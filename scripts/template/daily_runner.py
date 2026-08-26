from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from daily_collection import ClarityCollector, HttpResponse
from daily_report import generate_daily_alert
from source_snapshot import persist_source_snapshot
from warehouse import AnalyticsWarehouse
from retention import cleanup_raw_snapshots


CORE_SOURCES = ("ga4", "gsc", "google_ads", "shopify")
WEEKLY_WINDOW_DAYS = 14


@dataclass(frozen=True)
class SourceDataset:
    dataset: str
    raw_rows: list[dict[str, Any]]
    daily_metrics: list[dict[str, Any]]
    api_request_completed: bool
    query_start_date: str
    query_end_date: str
    manifest_metadata: dict[str, Any] | None = None


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
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("Daily ingestion now must be timezone-aware.")
        now = now.astimezone(timezone.utc).replace(microsecond=0)
        run_id = now.isoformat().replace("+00:00", "Z")
        report_now = now.astimezone(ZoneInfo(self.settings["REPORT_TIMEZONE"]))
        try:
            clarity = ClarityCollector(
                self.project_root, self.settings, transport=self.clarity_transport
            ).collect(now=now)
            clarity_successful_packs = clarity.successful_packs
        except Exception as error:
            self._record_clarity_failure(run_id, error)
            clarity_successful_packs = 0
        source_status: dict[str, str] = {}
        successful_query_windows: dict[str, tuple[date, date]] = {}
        local_yesterday = report_now.date() - timedelta(days=1)
        gsc_lag_days = int(self.settings.get("GSC_FINALIZED_LAG_DAYS", "3"))
        if gsc_lag_days < 1:
            raise ValueError("GSC_FINALIZED_LAG_DAYS must be at least 1.")
        source_end_dates = {
            source: (
                report_now.date() - timedelta(days=gsc_lag_days)
                if source == "gsc"
                else local_yesterday
            )
            for source in CORE_SOURCES
        }
        common_complete_end = min(source_end_dates.values())
        common_start = common_complete_end - timedelta(days=WEEKLY_WINDOW_DAYS - 1)
        for source in CORE_SOURCES:
            fetcher = self.source_fetchers.get(source)
            if not fetcher:
                source_status[source] = "not_configured"
                self._record_source_failure(source, run_id, RuntimeError("No source fetcher configured."))
                continue
            start = common_start
            source_end = source_end_dates[source]
            try:
                dataset = fetcher(self.settings, start.isoformat(), source_end.isoformat())
                manifest = persist_source_snapshot(
                    self.project_root,
                    self.warehouse,
                    source=source,
                    run_id=run_id,
                    dataset=dataset.dataset,
                    raw_rows=dataset.raw_rows,
                    daily_metrics=dataset.daily_metrics,
                    manifest_metadata=dataset.manifest_metadata,
                    api_request_completed=dataset.api_request_completed,
                    query_start_date=dataset.query_start_date,
                    query_end_date=dataset.query_end_date,
                    expected_start_date=start.isoformat(),
                    expected_end_date=source_end.isoformat(),
                )
                source_status[source] = manifest["status"]
                if manifest["status"] in {"complete", "valid_zero"}:
                    successful_query_windows[source] = (
                        date.fromisoformat(dataset.query_start_date),
                        date.fromisoformat(dataset.query_end_date),
                    )
            except Exception as error:
                source_status[source] = "failed"
                self._record_source_failure(source, run_id, error)
        generate_daily_alert(
            self.warehouse, self.project_root / "outputs", report_now.date().isoformat()
        )
        cleanup_raw_snapshots(
            self.project_root,
            retention_days=int(self.settings.get("RAW_RETENTION_DAYS", "400")),
            now=now,
        )
        weekly_report_path = None
        complete_statuses = {"complete", "valid_zero"}
        report_window_start = common_complete_end - timedelta(days=WEEKLY_WINDOW_DAYS - 1)
        report_window_is_current = all(
            source in successful_query_windows
            and successful_query_windows[source][0] <= report_window_start
            and successful_query_windows[source][1] >= common_complete_end
            for source in CORE_SOURCES
        )
        if report_window_is_current and all(
            source_status.get(source) in complete_statuses for source in CORE_SOURCES
        ):
            try:
                from ai_narrative import write_optional_narrative
                from reporting import generate_weekly_report

                weekly = generate_weekly_report(
                    self.warehouse,
                    self.project_root / "outputs",
                    expected_current_end=common_complete_end,
                )
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
