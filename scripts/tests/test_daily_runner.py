from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

try:
    import daily_runner
    import reporting
except ModuleNotFoundError:
    daily_runner = None
    reporting = None


def date_values(start: str, end: str) -> list[str]:
    first = date.fromisoformat(start)
    last = date.fromisoformat(end)
    return [
        (first + timedelta(days=offset)).isoformat()
        for offset in range((last - first).days + 1)
    ]


class DailyRunnerTests(unittest.TestCase):
    def test_runner_uses_bundled_fetchers_when_none_are_injected(self) -> None:
        self.assertIsNotNone(daily_runner)
        with tempfile.TemporaryDirectory() as directory:
            runner = daily_runner.DailyIngestionRunner(
                Path(directory),
                {
                    "CLARITY_PROJECT_ID": "project",
                    "CLARITY_EXPORT_TOKEN": "token",
                    "REPORT_TIMEZONE": "UTC",
                },
            )
            self.assertEqual(set(runner.source_fetchers), {"ga4", "gsc", "google_ads", "shopify"})

    def test_runner_persists_each_source_and_still_reports_partial_source_health(self) -> None:
        self.assertIsNotNone(daily_runner)

        def clarity_transport(url: str, headers: dict[str, str]) -> daily_runner.HttpResponse:
            body = json.dumps(
                [{"metricName": "Traffic", "information": [{"Url": "https://shop.test/p", "Device": "Mobile", "Channel": "Direct", "Source": "google", "Medium": "cpc", "Campaign": "brand", "Country/Region": "US", "totalSessionCount": "10"}]}]
            ).encode("utf-8")
            return daily_runner.HttpResponse(200, body)

        def source_rows(source: str):
            metrics = (
                {
                    "orders": 0,
                    "revenue": 0.0,
                    "online_store_orders": 0,
                    "online_store_revenue": 0.0,
                    "offsite_orders": 0,
                    "offsite_revenue": 0.0,
                }
                if source == "shopify"
                else {"sessions": 10.0}
            )
            return lambda settings, start, end: daily_runner.SourceDataset(
                dataset="daily",
                raw_rows=[] if source == "shopify" else [{"source": source}],
                daily_metrics=[{"date": value, **metrics} for value in date_values(start, end)],
                api_request_completed=True,
                query_start_date=start,
                query_end_date=end,
                manifest_metadata={"source": source},
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = daily_runner.DailyIngestionRunner(
                root,
                {
                    "CLARITY_PROJECT_ID": "project",
                    "CLARITY_EXPORT_TOKEN": "token",
                    "REPORT_TIMEZONE": "UTC",
                },
                clarity_transport=clarity_transport,
                source_fetchers={source: source_rows(source) for source in ("ga4", "gsc", "google_ads", "shopify")},
            )
            outcome = runner.run(now=datetime(2026, 7, 12, 0, 30, tzinfo=timezone.utc))
            self.assertEqual(outcome.source_status["shopify"], "valid_zero")
            self.assertEqual(outcome.source_status["ga4"], "complete")
            self.assertTrue((root / "outputs" / "daily_alert_2026-07-12.md").is_file())

    def test_runner_continues_four_source_collection_when_clarity_is_unavailable(self) -> None:
        self.assertIsNotNone(daily_runner)

        def source_rows(source: str):
            metrics = (
                {
                    "orders": 0,
                    "revenue": 0.0,
                    "online_store_orders": 0,
                    "online_store_revenue": 0.0,
                    "offsite_orders": 0,
                    "offsite_revenue": 0.0,
                }
                if source == "shopify"
                else {"sessions": 10.0}
            )
            return lambda settings, start, end: daily_runner.SourceDataset(
                dataset="daily",
                raw_rows=[],
                daily_metrics=[{"date": value, **metrics} for value in date_values(start, end)],
                api_request_completed=True,
                query_start_date=start,
                query_end_date=end,
                manifest_metadata={"source": source},
            )

        with tempfile.TemporaryDirectory() as directory:
            runner = daily_runner.DailyIngestionRunner(
                Path(directory),
                {"CLARITY_PROJECT_ID": "project", "REPORT_TIMEZONE": "UTC"},
                source_fetchers={source: source_rows(source) for source in ("ga4", "gsc", "google_ads", "shopify")},
            )
            outcome = runner.run(now=datetime(2026, 7, 12, 0, 30, tzinfo=timezone.utc))
            self.assertEqual(outcome.clarity_successful_packs, 0)
            self.assertEqual(outcome.source_status["shopify"], "valid_zero")
            self.assertTrue(
                all(outcome.source_status[source] == "complete" for source in ("ga4", "gsc", "google_ads"))
            )

    def test_runner_does_not_generate_weekly_report_when_current_source_fails(self) -> None:
        self.assertIsNotNone(daily_runner)

        def source_rows(source: str):
            if source == "gsc":
                def fail(settings, start, end):
                    raise RuntimeError("current GSC fetch failed")

                return fail
            metrics = (
                {
                    "orders": 0,
                    "revenue": 0.0,
                    "online_store_orders": 0,
                    "online_store_revenue": 0.0,
                    "offsite_orders": 0,
                    "offsite_revenue": 0.0,
                }
                if source == "shopify"
                else {"sessions": 1.0}
            )
            return lambda settings, start, end: daily_runner.SourceDataset(
                dataset="daily",
                raw_rows=[],
                daily_metrics=[{"date": value, **metrics} for value in date_values(start, end)],
                api_request_completed=True,
                query_start_date=start,
                query_end_date=end,
                manifest_metadata={"source": source},
            )

        with tempfile.TemporaryDirectory() as directory, patch("reporting.generate_weekly_report") as generate:
            runner = daily_runner.DailyIngestionRunner(
                Path(directory),
                {"CLARITY_PROJECT_ID": "project", "REPORT_TIMEZONE": "UTC"},
                source_fetchers={source: source_rows(source) for source in ("ga4", "gsc", "google_ads", "shopify")},
            )
            outcome = runner.run(now=datetime(2026, 7, 12, 0, 30, tzinfo=timezone.utc))
            self.assertEqual(outcome.source_status["gsc"], "failed")
            self.assertIsNone(outcome.weekly_report_path)
            generate.assert_not_called()

    def test_runner_rejects_fabricated_source_without_api_completion_proof(self) -> None:
        self.assertIsNotNone(daily_runner)

        def source_rows(source: str):
            metrics = (
                {
                    "orders": 0,
                    "revenue": 0.0,
                    "online_store_orders": 0,
                    "online_store_revenue": 0.0,
                    "offsite_orders": 0,
                    "offsite_revenue": 0.0,
                }
                if source == "shopify"
                else {"sessions": 0.0}
            )
            return lambda settings, start, end: daily_runner.SourceDataset(
                dataset="daily",
                raw_rows=[],
                daily_metrics=[{"date": value, **metrics} for value in date_values(start, end)],
                api_request_completed=source != "gsc",
                query_start_date=start,
                query_end_date=end,
                manifest_metadata={"source": source},
            )

        with tempfile.TemporaryDirectory() as directory:
            runner = daily_runner.DailyIngestionRunner(
                Path(directory),
                {"CLARITY_PROJECT_ID": "project", "REPORT_TIMEZONE": "UTC"},
                source_fetchers={
                    source: source_rows(source)
                    for source in ("ga4", "gsc", "google_ads", "shopify")
                },
            )
            outcome = runner.run(
                now=datetime(2026, 7, 12, 0, 30, tzinfo=timezone.utc)
            )
            self.assertEqual(outcome.source_status["gsc"], "failed")
            self.assertEqual(runner.warehouse.source_complete_dates("gsc"), set())

    def test_runner_uses_report_timezone_and_finalized_gsc_end(self) -> None:
        self.assertIsNotNone(daily_runner)
        requested_windows: list[tuple[str, str, str]] = []

        def source_rows(source: str):
            def fetch(settings, start, end):
                requested_windows.append((source, start, end))
                metrics = (
                    {
                        "orders": 0,
                        "revenue": 0.0,
                        "online_store_orders": 0,
                        "online_store_revenue": 0.0,
                        "offsite_orders": 0,
                        "offsite_revenue": 0.0,
                    }
                    if source == "shopify"
                    else {"sessions": 0.0}
                )
                return daily_runner.SourceDataset(
                    dataset="daily",
                    raw_rows=[],
                    daily_metrics=[
                        {"date": value, **metrics} for value in date_values(start, end)
                    ],
                    api_request_completed=True,
                    query_start_date=start,
                    query_end_date=end,
                    manifest_metadata={"source": source},
                )

            return fetch

        with tempfile.TemporaryDirectory() as directory:
            runner = daily_runner.DailyIngestionRunner(
                Path(directory),
                {
                    "CLARITY_PROJECT_ID": "project",
                    "REPORT_TIMEZONE": "America/Los_Angeles",
                },
                source_fetchers={
                    source: source_rows(source)
                    for source in ("ga4", "gsc", "google_ads", "shopify")
                },
            )
            runner.run(now=datetime(2026, 7, 12, 0, 30, tzinfo=timezone.utc))
        windows = {source: (start, end) for source, start, end in requested_windows}
        self.assertEqual(windows["gsc"], ("2026-06-25", "2026-07-08"))
        self.assertTrue(
            all(
                windows[source] == ("2026-06-25", "2026-07-10")
                for source in ("ga4", "google_ads", "shopify")
            )
        )

    def test_runner_rejects_old_week_when_current_statuses_are_only_stubbed_valid_zero(self) -> None:
        self.assertIsNotNone(daily_runner)
        self.assertIsNotNone(reporting)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = daily_runner.DailyIngestionRunner(
                root,
                {"CLARITY_PROJECT_ID": "project", "REPORT_TIMEZONE": "UTC"},
                source_fetchers={
                    source: (
                        lambda settings, start, end: daily_runner.SourceDataset(
                            dataset="daily",
                            raw_rows=[],
                            daily_metrics=[],
                            api_request_completed=True,
                            query_start_date=start,
                            query_end_date=end,
                            manifest_metadata={"source": "stub"},
                        )
                    )
                    for source in ("ga4", "gsc", "google_ads", "shopify")
                },
            )
            old_dates = date_values("2026-06-01", "2026-06-14")
            for source, rows in {
                "shopify": [
                    {
                        "date": value,
                        "orders": 0,
                        "revenue": 0.0,
                        "online_store_orders": 0,
                        "online_store_revenue": 0.0,
                        "offsite_orders": 0,
                        "offsite_revenue": 0.0,
                    }
                    for value in old_dates
                ],
                "ga4": [{"date": value, "sessions": 0.0} for value in old_dates],
                "google_ads": [{"date": value, "ad_spend": 0.0} for value in old_dates],
                "gsc": [{"date": value, "seo_clicks": 0.0} for value in old_dates],
            }.items():
                runner.warehouse.persist_source_daily_metrics(
                    source, "old", rows, status="valid_zero"
                )
            with patch(
                "daily_runner.persist_source_snapshot",
                return_value={"status": "valid_zero"},
            ), patch(
                "reporting.generate_weekly_report",
                wraps=reporting.generate_weekly_report,
            ) as generate:
                outcome = runner.run(
                    now=datetime(2026, 7, 20, 0, 30, tzinfo=timezone.utc)
                )
            self.assertIsNone(outcome.weekly_report_path)
            self.assertEqual(
                generate.call_args.kwargs["expected_current_end"], date(2026, 7, 17)
            )


if __name__ == "__main__":
    unittest.main()
