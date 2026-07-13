from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from clarity_export import ClarityRunLedger, QUERY_PACKS, parse_clarity_payload
from warehouse import AnalyticsWarehouse


CLARITY_ENDPOINT = "https://www.clarity.ms/export-data/api/v1/project-live-insights"


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes


@dataclass(frozen=True)
class CollectionOutcome:
    successful_packs: int
    failed_packs: int
    skipped_packs: int
    manifests: list[dict[str, Any]]


Transport = Callable[[str, dict[str, str]], HttpResponse]


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_snapshot_id(snapshot_id: str) -> str:
    return snapshot_id.replace(":", "-")


def _default_transport(url: str, headers: dict[str, str]) -> HttpResponse:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            return HttpResponse(status=int(response.status), body=response.read())
    except Exception as error:  # urllib exposes different concrete network errors by platform.
        status = getattr(error, "code", 599)
        body = str(error).encode("utf-8", errors="replace")
        return HttpResponse(status=int(status), body=body)


class ClarityCollector:
    def __init__(
        self,
        project_root: Path,
        settings: dict[str, str],
        *,
        transport: Transport | None = None,
    ) -> None:
        self.project_root = project_root
        self.settings = settings
        self.transport = transport or _default_transport
        self.ledger = ClarityRunLedger(project_root / "data" / "state" / "clarity_runs.jsonl")
        self.warehouse = AnalyticsWarehouse(project_root)

    def _request_url(self, query_pack: str) -> str:
        parameters: dict[str, str] = {"numOfDays": "1"}
        for index, dimension in enumerate(QUERY_PACKS[query_pack], start=1):
            parameters[f"dimension{index}"] = dimension
        return f"{CLARITY_ENDPOINT}?{urlencode(parameters)}"

    def _raw_directory(self, snapshot_id: str, query_pack: str) -> Path:
        return (
            self.project_root
            / "data"
            / "raw"
            / "clarity"
            / f"snapshot_id={_safe_snapshot_id(snapshot_id)}"
            / f"query_pack={query_pack}"
        )

    def collect(self, now: datetime | None = None) -> CollectionOutcome:
        if not self.settings.get("CLARITY_EXPORT_TOKEN"):
            raise RuntimeError("Missing CLARITY_EXPORT_TOKEN.")
        if not self.settings.get("CLARITY_PROJECT_ID"):
            raise RuntimeError("Missing CLARITY_PROJECT_ID.")
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("Clarity collection time must be timezone-aware UTC.")
        now = now.astimezone(timezone.utc).replace(microsecond=0)
        snapshot_hour = int(self.settings.get("CLARITY_SNAPSHOT_UTC_HOUR", "0"))
        snapshot_minute = int(self.settings.get("CLARITY_SNAPSHOT_UTC_MINUTE", "0"))
        if not (0 <= snapshot_hour <= 23 and 0 <= snapshot_minute <= 59):
            raise ValueError("CLARITY_SNAPSHOT_UTC_HOUR/MINUTE must define a UTC clock time.")
        anchor = now.replace(hour=snapshot_hour, minute=snapshot_minute, second=0)
        if now < anchor:
            anchor -= timedelta(days=1)
        snapshot_id = _format_utc(anchor)
        window_start = _format_utc(anchor - timedelta(days=1))
        window_end = snapshot_id
        manifests: list[dict[str, Any]] = []
        successful = failed = skipped = 0
        headers = {"Authorization": f"Bearer {self.settings['CLARITY_EXPORT_TOKEN']}"}

        for query_pack in QUERY_PACKS:
            retry = False
            while True:
                if not self.ledger.reserve(snapshot_id, query_pack, allow_retry=retry):
                    skipped += 1
                    break
                response = self.transport(self._request_url(query_pack), headers)
                if response.status == 200 and response.body:
                    try:
                        payload = json.loads(response.body.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as error:
                        self.ledger.fail(snapshot_id, query_pack, f"invalid_json: {error}")
                        failed += 1
                        break
                    if not isinstance(payload, list):
                        self.ledger.fail(snapshot_id, query_pack, "invalid_payload: expected JSON array")
                        failed += 1
                        break
                    parsed = parse_clarity_payload(payload, query_pack=query_pack, snapshot_id=snapshot_id)
                    metric_row_counts = parsed.metric_row_counts
                    total_rows = sum(metric_row_counts.values())
                    largest_metric_rows = max(metric_row_counts.values(), default=0)
                    raw_directory = self._raw_directory(snapshot_id, query_pack)
                    raw_directory.mkdir(parents=True, exist_ok=True)
                    response_path = raw_directory / "response.json"
                    response_path.write_bytes(response.body)
                    manifest = {
                        "snapshot_id": snapshot_id,
                        "query_pack": query_pack,
                        "project_id": self.settings["CLARITY_PROJECT_ID"],
                        "dimensions": list(QUERY_PACKS[query_pack]),
                        "num_of_days": 1,
                        "snapshot_window_start_utc": window_start,
                        "snapshot_window_end_utc": window_end,
                        "fetched_at_utc": _format_utc(datetime.now(timezone.utc)),
                        "http_status": response.status,
                        "response_hash": hashlib.sha256(response.body).hexdigest(),
                        "response_bytes": len(response.body),
                        "row_count": total_rows,
                        "largest_metric_row_count": largest_metric_rows,
                        "truncation_risk": largest_metric_rows >= 1000,
                        "coverage_status": "partial" if largest_metric_rows >= 1000 else "complete",
                        "schema_mismatch": parsed.schema_mismatch,
                        "metric_row_counts": metric_row_counts,
                        "raw_response_path": str(response_path),
                    }
                    (raw_directory / "manifest.json").write_text(
                        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                        encoding="utf-8",
                    )
                    self.ledger.complete(
                        snapshot_id,
                        query_pack,
                        response_hash=manifest["response_hash"],
                        row_count=largest_metric_rows,
                    )
                    if not parsed.schema_mismatch and not manifest["truncation_risk"]:
                        self.warehouse.persist_clarity_snapshot(manifest, parsed)
                    manifests.append(manifest)
                    successful += 1
                    break

                error = f"http_status={response.status}; body={response.body[:200].decode('utf-8', errors='replace')}"
                self.ledger.fail(snapshot_id, query_pack, error)
                if not retry and response.status >= 500:
                    retry = True
                    continue
                failed += 1
                break
        return CollectionOutcome(successful, failed, skipped, manifests)
