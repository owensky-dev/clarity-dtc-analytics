from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from daily_collection import ClarityCollector, HttpResponse
from daily_report import generate_daily_alert
from source_snapshot import persist_source_snapshot
from warehouse import AnalyticsWarehouse
from retention import cleanup_raw_snapshots


CORE_SOURCES = ("ga4", "gsc", "google_ads", "shopify")
LOOKBACK_DAYS = {"ga4": 4, "gsc": 4, "google_ads": 3, "shopify": 7}


@dataclass(frozen=True)
class SourceDataset:
    dataset: str
    raw_rows: list[dict[str, Any]]
    daily_metrics: list[dict[str, Any]]


@dataclass(frozen=True)
class DailyRunOutcome:
    clarity_successful_packs: int
    source_status: dict[str, str]
    weekly_report_path: Path | None


SourceFetcher = Callable[[dict[str, str], str, str], SourceDataset]


class DailyIngestionRunner:
    def __init__(
        self,
        project_root: Path,
        settings: dict[str, str],
        *,
        clarity_transport: Any | None = None,
        source_fetchers: dict[str, SourceFetcher] | None = None,
    ) -> None:
        self.project_root = project_root
        self.settings = settings
        self.warehouse = AnalyticsWarehouse(project_root)
        self.clarity_transport = clarity_transport
        if source_fetchers is None:
            from source_fetchers import default_source_fetchers

            self.source_fetchers = default_source_fetchers()
        else:
            self.source_fetchers = source_fetchers

    def _record_source_failure(self, source: str, run_id: str, error: Exception) -> None:
        output_dir = self.project_root / "data" / "raw" / source / f"run_id={run_id.replace(':', '-')}"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "failure.manifest.json").write_text(
            json.dumps({"source": source, "run_id": run_id, "status": "failed", "error": str(error)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _record_clarity_failure(self, run_id: str, error: Exception) -> None:
        output_dir = self.project_root / "data" / "raw" / "clarity" / f"run_id={run_id.replace(':', '-')}"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "failure.manifest.json").write_text(
            json.dumps({"source": "clarity", "run_id": run_id, "status": "failed", "error": str(error)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def run(self, now: datetime | None = None) -> DailyRunOutcome:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
        run_id = now.isoformat().replace("+00:00", "Z")
        try:
            clarity = ClarityCollector(
                self.project_root, self.settings, transport=self.clarity_transport
            ).collect(now=now)
            clarity_successful_packs = clarity.successful_packs
        except Exception as error:
            self._record_clarity_failure(run_id, error)
            clarity_successful_packs = 0
        source_status: dict[str, str] = {}
        logical_end = now.date() - timedelta(days=1)
        for source in CORE_SOURCES:
            fetcher = self.source_fetchers.get(source)
            if not fetcher:
                source_status[source] = "not_configured"
                self._record_source_failure(source, run_id, RuntimeError("No source fetcher configured."))
                continue
            start = logical_end - timedelta(days=LOOKBACK_DAYS[source] - 1)
            try:
                dataset = fetcher(self.settings, start.isoformat(), logical_end.isoformat())
                manifest = persist_source_snapshot(
                    self.project_root,
                    self.warehouse,
                    source=source,
                    run_id=run_id,
                    dataset=dataset.dataset,
                    raw_rows=dataset.raw_rows,
                    daily_metrics=dataset.daily_metrics,
                )
                source_status[source] = manifest["status"]
            except Exception as error:
                source_status[source] = "failed"
                self._record_source_failure(source, run_id, error)
        generate_daily_alert(self.warehouse, self.project_root / "outputs", now.date().isoformat())
        cleanup_raw_snapshots(
            self.project_root,
            retention_days=int(self.settings.get("RAW_RETENTION_DAYS", "400")),
            now=now,
        )
        weekly_report_path = None
        try:
            from ai_narrative import write_optional_narrative
            from reporting import generate_weekly_report

            weekly = generate_weekly_report(self.warehouse, self.project_root / "outputs")
            write_optional_narrative(
                weekly.payload,
                self.settings,
                weekly.json_path.with_name(weekly.json_path.stem + "_ai.md"),
            )
            weekly_report_path = weekly.html_path
        except Exception:
            # Daily collection must remain useful before a full four-source history exists.
            pass
        return DailyRunOutcome(
            clarity_successful_packs=clarity_successful_packs,
            source_status=source_status,
            weekly_report_path=weekly_report_path,
        )
