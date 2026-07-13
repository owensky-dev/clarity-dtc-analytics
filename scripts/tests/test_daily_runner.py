from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

try:
    import daily_runner
except ModuleNotFoundError:
    daily_runner = None


class DailyRunnerTests(unittest.TestCase):
    def test_runner_uses_bundled_fetchers_when_none_are_injected(self) -> None:
        self.assertIsNotNone(daily_runner)
        with tempfile.TemporaryDirectory() as directory:
            runner = daily_runner.DailyIngestionRunner(
                Path(directory),
                {"CLARITY_PROJECT_ID": "project", "CLARITY_EXPORT_TOKEN": "token"},
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
            return lambda settings, start, end: daily_runner.SourceDataset(
                dataset="daily",
                raw_rows=[{"source": source}],
                daily_metrics=[{"date": "2026-07-11", **({"orders": 0, "revenue": 0.0} if source == "shopify" else {"sessions": 10.0})}],
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = daily_runner.DailyIngestionRunner(
                root,
                {"CLARITY_PROJECT_ID": "project", "CLARITY_EXPORT_TOKEN": "token"},
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
            return lambda settings, start, end: daily_runner.SourceDataset(
                dataset="daily", raw_rows=[], daily_metrics=[{"date": "2026-07-11", "orders": 0, "revenue": 0.0}]
            )

        with tempfile.TemporaryDirectory() as directory:
            runner = daily_runner.DailyIngestionRunner(
                Path(directory),
                {"CLARITY_PROJECT_ID": "project"},
                source_fetchers={source: source_rows(source) for source in ("ga4", "gsc", "google_ads", "shopify")},
            )
            outcome = runner.run(now=datetime(2026, 7, 12, 0, 30, tzinfo=timezone.utc))
            self.assertEqual(outcome.clarity_successful_packs, 0)
            self.assertTrue(all(status == "valid_zero" for status in outcome.source_status.values()))


if __name__ == "__main__":
    unittest.main()
