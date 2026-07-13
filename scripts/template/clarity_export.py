from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline_core import canonical_url, normalize_device

MAX_DAILY_REQUESTS = 10
MAX_RESPONSE_ROWS = 1000
QUERY_PACKS = {
    "overall": (),
    "url_device_channel": ("URL", "Device", "Channel"),
    "source_medium_campaign": ("Source", "Medium", "Campaign"),
    "url_country_device": ("URL", "Country/Region", "Device"),
}


@dataclass(frozen=True)
class ClarityQuery:
    name: str
    dimensions: tuple[str, ...]


@dataclass(frozen=True)
class ParsedClarityPayload:
    metric_rows: list[dict[str, Any]]
    metric_row_counts: dict[str, int]
    schema_mismatch: bool


DIMENSION_FIELDS = {
    "URL": ("Url", "URL"),
    "Device": ("Device",),
    "Channel": ("Channel",),
    "Source": ("Source",),
    "Medium": ("Medium",),
    "Campaign": ("Campaign",),
    "Country/Region": ("Country/Region", "CountryRegion", "Country"),
    "OS": ("OS",),
    "Browser": ("Browser",),
}
NUMERIC_FIELDS = {
    "totalSessionCount",
    "totalBotSessionCount",
    "distinctUserCount",
    "pagesPerSessionPercentage",
    "sessionsCount",
    "sessionsWithMetricPercentage",
    "sessionsWithoutMetricPercentage",
    "pagesViews",
    "subTotal",
    "averageScrollDepth",
    "totalTime",
    "activeTime",
}
METRIC_VALUE_FIELDS = {
    "Traffic": ("total_sessions", "totalSessionCount"),
    "DeadClickCount": ("dead_click_count", "subTotal"),
    "RageClickCount": ("rage_click_count", "subTotal"),
    "ErrorClickCount": ("error_click_count", "subTotal"),
    "ScriptErrorCount": ("script_error_count", "subTotal"),
    "QuickbackClick": ("quickback_click_count", "subTotal"),
    "ExcessiveScroll": ("excessive_scroll_count", "subTotal"),
    "ScrollDepth": ("average_scroll_depth", "averageScrollDepth"),
    "EngagementTime": ("active_time_seconds", "activeTime"),
}


def _dimension_value(payload: dict[str, Any], dimension: str) -> Any:
    for field in DIMENSION_FIELDS[dimension]:
        if field in payload:
            return payload[field]
    return None


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_clarity_payload(
    payload: list[dict[str, Any]], *, query_pack: str, snapshot_id: str
) -> ParsedClarityPayload:
    """Preserve each Clarity metric row and validate expected response dimensions."""
    if query_pack not in QUERY_PACKS:
        raise ValueError(f"Unknown Clarity query pack: {query_pack}")
    if not isinstance(payload, list):
        raise ValueError("Clarity export payload must be a JSON array.")

    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    observed_fields: set[str] = set()
    for metric in payload:
        metric_name = str(metric.get("metricName", "unknown"))
        information = metric.get("information") or []
        if not isinstance(information, list):
            continue
        counts[metric_name] = len(information)
        for row_index, information_row in enumerate(information):
            if not isinstance(information_row, dict):
                continue
            dimensions = {
                dimension: _dimension_value(information_row, dimension)
                for dimension in DIMENSION_FIELDS
            }
            for dimension, aliases in DIMENSION_FIELDS.items():
                if any(alias in information_row for alias in aliases):
                    observed_fields.add(dimension)
            numeric = {
                field: number
                for field in NUMERIC_FIELDS
                if (number := _number(information_row.get(field))) is not None
            }
            raw_url = dimensions["URL"]
            rows.append(
                {
                    "snapshot_id": snapshot_id,
                    "query_pack": query_pack,
                    "metric_name": metric_name,
                    "row_index": row_index,
                    "raw_url": raw_url,
                    "canonical_url": canonical_url(raw_url),
                    "device": normalize_device(dimensions["Device"]),
                    "channel": dimensions["Channel"],
                    "dimensions": dimensions,
                    "dimensions_json": json.dumps(dimensions, ensure_ascii=False, sort_keys=True),
                    "numeric": numeric,
                    "raw_information_json": json.dumps(information_row, ensure_ascii=False, sort_keys=True),
                }
            )
    expected = set(QUERY_PACKS[query_pack])
    return ParsedClarityPayload(
        metric_rows=rows,
        metric_row_counts=counts,
        schema_mismatch=bool(expected - observed_fields),
    )


def build_behavior_facts(metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create a report-friendly view while preserving the original long rows separately."""
    facts: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in metric_rows:
        dimensions = row["dimensions"]
        key = (
            row["snapshot_id"],
            row["query_pack"],
            row["canonical_url"],
            row["device"],
            dimensions["Channel"],
            dimensions["Source"],
            dimensions["Medium"],
            dimensions["Campaign"],
            dimensions["Country/Region"],
        )
        fact = facts.setdefault(
            key,
            {
                "snapshot_id": row["snapshot_id"],
                "query_pack": row["query_pack"],
                "raw_url": row["raw_url"],
                "canonical_url": row["canonical_url"],
                "device": row["device"],
                "channel": dimensions["Channel"],
                "source": dimensions["Source"],
                "medium": dimensions["Medium"],
                "campaign": dimensions["Campaign"],
                "country_region": dimensions["Country/Region"],
            },
        )
        mapped = METRIC_VALUE_FIELDS.get(row["metric_name"])
        if mapped:
            target, source = mapped
            value = row["numeric"].get(source)
            if value is not None:
                fact[target] = value
    return list(facts.values())


class ClarityRunLedger:
    """Append-only state for quota checks and idempotent Clarity snapshots."""

    def __init__(self, path: Path, max_daily_requests: int = MAX_DAILY_REQUESTS) -> None:
        self.path = path
        self.max_daily_requests = max_daily_requests

    def _entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows

    def _latest_entries(self) -> dict[tuple[str, str], dict[str, Any]]:
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for item in self._entries():
            run_id = str(item.get("run_id", ""))
            query_pack = str(item.get("query_pack", ""))
            if run_id and query_pack:
                latest[(run_id, query_pack)] = item
        return latest

    def _append(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def request_count(self, utc_date: str) -> int:
        return sum(
            int(item.get("attempt", 1))
            for (run_id, _), item in self._latest_entries().items()
            if run_id.startswith(utc_date)
            and item.get("status") in {"reserved", "success", "partial", "failed", "schema_mismatch"}
        )

    def entry(self, run_id: str, query_pack: str) -> dict[str, Any]:
        return dict(self._latest_entries().get((run_id, query_pack), {}))

    def reserve(self, run_id: str, query_pack: str, allow_retry: bool = False) -> bool:
        if query_pack not in QUERY_PACKS:
            raise ValueError(f"Unknown Clarity query pack: {query_pack}")
        prior = self.entry(run_id, query_pack)
        if prior and not (
            allow_retry
            and prior.get("status") == "failed"
            and int(prior.get("attempt", 1)) < 2
        ):
            return False
        utc_date = run_id[:10]
        if self.request_count(utc_date) >= self.max_daily_requests:
            return False
        attempt = int(prior.get("attempt", 0)) + 1 if prior else 1
        self._append(
            {
                "run_id": run_id,
                "query_pack": query_pack,
                "dimensions": list(QUERY_PACKS[query_pack]),
                "attempt": attempt,
                "status": "reserved",
                "truncation_risk": False,
            }
        )
        return True

    def complete(
        self,
        run_id: str,
        query_pack: str,
        *,
        response_hash: str,
        row_count: int,
    ) -> None:
        prior = self.entry(run_id, query_pack)
        if not prior:
            raise RuntimeError("Reserve a Clarity query before recording its result.")
        truncated = row_count >= MAX_RESPONSE_ROWS
        self._append(
            {
                **prior,
                "response_hash": response_hash,
                "row_count": row_count,
                "status": "partial" if truncated else "success",
                "truncation_risk": truncated,
            }
        )

    def fail(self, run_id: str, query_pack: str, error: str) -> None:
        prior = self.entry(run_id, query_pack)
        if not prior:
            raise RuntimeError("Reserve a Clarity query before recording its failure.")
        self._append({**prior, "status": "failed", "error": error})
