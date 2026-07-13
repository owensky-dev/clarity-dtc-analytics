from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

try:
    import pipeline_core
except ModuleNotFoundError:
    pipeline_core = None

try:
    import clarity_export
except ModuleNotFoundError:
    clarity_export = None


class CoreContractTests(unittest.TestCase):
    def test_canonical_url_and_device_mapping_remove_tracking_noise(self) -> None:
        self.assertIsNotNone(
            pipeline_core,
            "pipeline_core must expose canonical_url and normalize_device for the project template",
        )
        raw_url = (
            "HTTPS://Example.com/products/door/?utm_source=google&gclid=abc"
            "&variant=123#details"
        )
        self.assertEqual(
            pipeline_core.canonical_url(raw_url),
            "https://example.com/products/door",
        )
        self.assertEqual(pipeline_core.normalize_device("PC"), "desktop")
        self.assertEqual(pipeline_core.normalize_device("ChromeMobile"), "mobile")

    def test_clarity_ledger_marks_duplicate_and_truncated_snapshot(self) -> None:
        self.assertIsNotNone(
            clarity_export,
            "clarity_export must provide the local API-quota ledger",
        )
        with tempfile.TemporaryDirectory() as directory:
            ledger = clarity_export.ClarityRunLedger(Path(directory) / "runs.jsonl")
            run_id = "2026-07-12T00:30:00Z"
            self.assertTrue(ledger.reserve(run_id, "overall"))
            ledger.complete(
                run_id,
                "overall",
                response_hash="fixture-hash",
                row_count=1000,
            )
            self.assertFalse(ledger.reserve(run_id, "overall"))
            entry = ledger.entry(run_id, "overall")
            self.assertEqual(entry["status"], "partial")
            self.assertTrue(entry["truncation_risk"])
            self.assertEqual(ledger.request_count(run_id[:10]), 1)

    def test_clarity_ledger_allows_one_failed_request_retry_within_daily_quota(self) -> None:
        self.assertIsNotNone(clarity_export)
        with tempfile.TemporaryDirectory() as directory:
            ledger = clarity_export.ClarityRunLedger(Path(directory) / "runs.jsonl")
            run_id = "2026-07-12T00:30:00Z"
            self.assertTrue(ledger.reserve(run_id, "overall"))
            ledger.fail(run_id, "overall", "temporary network failure")
            self.assertTrue(ledger.reserve(run_id, "overall", allow_retry=True))
            self.assertEqual(ledger.request_count(run_id[:10]), 2)
            ledger.fail(run_id, "overall", "temporary network failure")
            self.assertFalse(ledger.reserve(run_id, "overall", allow_retry=True))

    def test_clarity_normalizer_joins_metrics_by_dimensions_not_array_order(self) -> None:
        self.assertIsNotNone(clarity_export)
        payload = [
            {
                "metricName": "Traffic",
                "information": [
                    {"Url": "https://shop.test/products/a?utm_source=x", "Device": "PC", "Channel": "Direct", "totalSessionCount": "20"},
                    {"Url": "https://shop.test/products/b", "Device": "Mobile", "Channel": "PaidSearch", "totalSessionCount": "10"},
                ],
            },
            {
                "metricName": "RageClickCount",
                "information": [
                    {"Url": "https://shop.test/products/b", "Device": "Mobile", "Channel": "PaidSearch", "subTotal": "2", "sessionsCount": "10"},
                    {"Url": "https://shop.test/products/a?gclid=1", "Device": "PC", "Channel": "Direct", "subTotal": "1", "sessionsCount": "20"},
                ],
            },
        ]
        parsed = clarity_export.parse_clarity_payload(
            payload,
            query_pack="url_device_channel",
            snapshot_id="2026-07-12T00:30:00Z",
        )
        self.assertEqual(len(parsed.metric_rows), 4)
        self.assertEqual(parsed.metric_rows[0]["metric_name"], "Traffic")
        self.assertEqual(parsed.metric_rows[0]["row_index"], 0)
        self.assertFalse(parsed.schema_mismatch)
        facts = clarity_export.build_behavior_facts(parsed.metric_rows)
        by_url = {row["canonical_url"]: row for row in facts}
        self.assertEqual(by_url["https://shop.test/products/a"]["total_sessions"], 20.0)
        self.assertEqual(by_url["https://shop.test/products/a"]["rage_click_count"], 1.0)
        self.assertEqual(by_url["https://shop.test/products/b"]["total_sessions"], 10.0)
        self.assertEqual(by_url["https://shop.test/products/b"]["rage_click_count"], 2.0)


if __name__ == "__main__":
    unittest.main()
