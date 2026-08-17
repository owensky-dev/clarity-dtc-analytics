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
    import daily_collection
except ModuleNotFoundError:
    daily_collection = None


class DailyCollectionTests(unittest.TestCase):
    def test_daily_collector_saves_four_query_packs_with_utc_manifest(self) -> None:
        self.assertIsNotNone(
            daily_collection,
            "daily_collection must collect the fixed Clarity query pack safely",
        )
        calls: list[str] = []

        def transport(url: str, headers: dict[str, str]) -> daily_collection.HttpResponse:
            calls.append(url)
            self.assertIn("Bearer token", headers["Authorization"])
            body = json.dumps(
                [
                    {
                        "metricName": "Traffic",
                        "information": [
                            {
                                "Url": "https://shop.test/products/a?utm_source=google",
                                "Device": "Mobile",
                                "Channel": "PaidSearch",
                                "Source": "google",
                                "Medium": "cpc",
                                "Campaign": "brand",
                                "Country/Region": "US",
                                "totalSessionCount": "12",
                            }
                        ],
                    }
                ]
            ).encode("utf-8")
            return daily_collection.HttpResponse(status=200, body=body)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collector = daily_collection.ClarityCollector(
                root,
                {"CLARITY_PROJECT_ID": "project", "CLARITY_EXPORT_TOKEN": "token"},
                transport=transport,
            )
            outcome = collector.collect(now=datetime(2026, 7, 12, 0, 30, tzinfo=timezone.utc))
            self.assertEqual(outcome.successful_packs, 4)
            self.assertEqual(len(calls), 4)
            manifest = json.loads(
                (root / "data" / "raw" / "clarity" / "snapshot_id=2026-07-12T00-00-00Z" / "query_pack=overall" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["snapshot_window_start_utc"], "2026-07-11T00:00:00Z")
            self.assertEqual(manifest["snapshot_window_end_utc"], "2026-07-12T00:00:00Z")
            self.assertFalse(manifest["schema_mismatch"])

    def test_same_utc_roll_window_is_idempotent_and_partial_data_is_not_warehoused(self) -> None:
        self.assertIsNotNone(daily_collection)

        def transport(url: str, headers: dict[str, str]) -> daily_collection.HttpResponse:
            body = json.dumps(
                [{"metricName": "Traffic", "information": [
                    {"Url": "https://shop.test/products/a", "Device": "Mobile", "Channel": "Direct", "totalSessionCount": "1"}
                    for _ in range(1000)
                ]}]
            ).encode("utf-8")
            return daily_collection.HttpResponse(status=200, body=body)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collector = daily_collection.ClarityCollector(
                root,
                {"CLARITY_PROJECT_ID": "project", "CLARITY_EXPORT_TOKEN": "token"},
                transport=transport,
            )
            first = collector.collect(now=datetime(2026, 7, 12, 0, 30, tzinfo=timezone.utc))
            second = collector.collect(now=datetime(2026, 7, 12, 8, 30, tzinfo=timezone.utc))
            self.assertEqual(first.successful_packs, 0)
            self.assertEqual(first.failed_packs, 4)
            self.assertEqual(second.skipped_packs, 4)
            self.assertEqual(collector.warehouse.count_rows("clarity_behavior_facts"), 0)
            manifest = json.loads(
                (root / "data" / "raw" / "clarity" / "snapshot_id=2026-07-12T00-00-00Z" / "query_pack=overall" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertTrue(manifest["truncation_risk"])
            self.assertEqual(manifest["coverage_status"], "partial")

    def test_url_country_device_without_country_region_is_saved_as_degraded_complete(self) -> None:
        self.assertIsNotNone(daily_collection)

        def transport(url: str, headers: dict[str, str]) -> daily_collection.HttpResponse:
            row = {
                "Url": "https://shop.test/products/a",
                "Device": "Mobile",
                "Channel": "Direct",
                "Source": "google",
                "Medium": "cpc",
                "Campaign": "brand",
                "Country/Region": "US",
                "totalSessionCount": "1",
            }
            if "dimension2=Country%2FRegion" in url:
                row.pop("Country/Region")
            body = json.dumps([{"metricName": "Traffic", "information": [row]}]).encode("utf-8")
            return daily_collection.HttpResponse(status=200, body=body)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collector = daily_collection.ClarityCollector(
                root,
                {"CLARITY_PROJECT_ID": "project", "CLARITY_EXPORT_TOKEN": "token"},
                transport=transport,
            )
            outcome = collector.collect(now=datetime(2026, 7, 12, 0, 30, tzinfo=timezone.utc))
            self.assertEqual(outcome.successful_packs, 4)
            self.assertEqual(outcome.failed_packs, 0)
            manifest = json.loads(
                (
                    root
                    / "data"
                    / "raw"
                    / "clarity"
                    / "snapshot_id=2026-07-12T00-00-00Z"
                    / "query_pack=url_country_device"
                    / "manifest.json"
                ).read_text(encoding="utf-8")
            )
            self.assertFalse(manifest["schema_mismatch"])
            self.assertEqual(manifest["missing_dimensions"], ["Country/Region"])
            self.assertEqual(manifest["degraded_dimensions"], ["Country/Region"])
            self.assertEqual(
                collector.ledger.entry("2026-07-12T00:00:00Z", "url_country_device")["status"],
                "success",
            )
            self.assertEqual(collector.warehouse.count_rows("clarity_behavior_facts"), 4)

    def test_url_country_device_still_fails_when_url_or_device_is_missing(self) -> None:
        self.assertIsNotNone(daily_collection)

        def transport(url: str, headers: dict[str, str]) -> daily_collection.HttpResponse:
            row = {
                "Url": "https://shop.test/products/a",
                "Device": "Mobile",
                "Channel": "Direct",
                "Source": "google",
                "Medium": "cpc",
                "Campaign": "brand",
                "Country/Region": "US",
                "totalSessionCount": "1",
            }
            if "dimension2=Country%2FRegion" in url:
                row.pop("Url")
            body = json.dumps([{"metricName": "Traffic", "information": [row]}]).encode("utf-8")
            return daily_collection.HttpResponse(status=200, body=body)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collector = daily_collection.ClarityCollector(
                root,
                {"CLARITY_PROJECT_ID": "project", "CLARITY_EXPORT_TOKEN": "token"},
                transport=transport,
            )
            outcome = collector.collect(now=datetime(2026, 7, 12, 0, 30, tzinfo=timezone.utc))
            self.assertEqual(outcome.successful_packs, 3)
            self.assertEqual(outcome.failed_packs, 1)
            manifest = json.loads(
                (
                    root
                    / "data"
                    / "raw"
                    / "clarity"
                    / "snapshot_id=2026-07-12T00-00-00Z"
                    / "query_pack=url_country_device"
                    / "manifest.json"
                ).read_text(encoding="utf-8")
            )
            self.assertTrue(manifest["schema_mismatch"])
            self.assertEqual(manifest["missing_dimensions"], ["URL"])

    def test_dns_failures_can_be_retried_by_later_health_check(self) -> None:
        self.assertIsNotNone(daily_collection)

        def dns_failure(url: str, headers: dict[str, str]) -> daily_collection.HttpResponse:
            return daily_collection.HttpResponse(
                status=599,
                body=b"<urlopen error [Errno 8] nodename nor servname provided, or not known>",
            )

        success_calls: list[str] = []

        def success(url: str, headers: dict[str, str]) -> daily_collection.HttpResponse:
            success_calls.append(url)
            body = json.dumps(
                [
                    {
                        "metricName": "Traffic",
                        "information": [
                            {
                                "Url": "https://shop.test/products/a",
                                "Device": "Mobile",
                                "Channel": "Direct",
                                "Source": "google",
                                "Medium": "cpc",
                                "Campaign": "brand",
                                "Country/Region": "US",
                                "totalSessionCount": "1",
                            }
                        ],
                    }
                ]
            ).encode("utf-8")
            return daily_collection.HttpResponse(status=200, body=body)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = {"CLARITY_PROJECT_ID": "project", "CLARITY_EXPORT_TOKEN": "token"}
            first = daily_collection.ClarityCollector(root, settings, transport=dns_failure).collect(
                now=datetime(2026, 7, 12, 0, 30, tzinfo=timezone.utc)
            )
            second = daily_collection.ClarityCollector(root, settings, transport=success).collect(
                now=datetime(2026, 7, 12, 8, 30, tzinfo=timezone.utc)
            )
            self.assertEqual(first.successful_packs, 0)
            self.assertEqual(second.successful_packs, 4)
            self.assertEqual(len(success_calls), 4)


if __name__ == "__main__":
    unittest.main()
