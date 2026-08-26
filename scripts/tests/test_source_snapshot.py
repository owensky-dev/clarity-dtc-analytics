from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

try:
    import source_metrics
    import source_snapshot
    import warehouse
except ModuleNotFoundError:
    source_metrics = None
    source_snapshot = None
    warehouse = None


class SourceSnapshotTests(unittest.TestCase):
    def test_snapshot_writer_records_zero_shopify_day_as_valid_data(self) -> None:
        self.assertIsNotNone(source_snapshot)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = source_snapshot.persist_source_snapshot(
                root,
                warehouse.AnalyticsWarehouse(root),
                source="shopify",
                run_id="2026-07-12T00:30:00Z",
                dataset="orders",
                raw_rows=[],
                daily_metrics=[
                    {
                        "date": "2026-07-11",
                        "orders": 0,
                        "revenue": 0.0,
                        "online_store_orders": 0,
                        "online_store_revenue": 0.0,
                        "offsite_orders": 0,
                        "offsite_revenue": 0.0,
                    }
                ],
                manifest_metadata={"business_order_filter": "paid_non_test_non_cancelled"},
            )
            self.assertEqual(manifest["status"], "valid_zero")
            self.assertEqual(manifest["date_range"], ["2026-07-11", "2026-07-11"])
            raw_path = root / "data" / "raw" / "shopify" / "run_id=2026-07-12T00-30-00Z" / "orders.json"
            self.assertEqual(json.loads(raw_path.read_text(encoding="utf-8")), [])
            self.assertIn("online_store_orders", manifest["daily_metric_schema"])
            self.assertEqual(manifest["contract"]["business_order_filter"], "paid_non_test_non_cancelled")

    def test_snapshot_writer_marks_empty_daily_metrics_failed_without_coverage(self) -> None:
        self.assertIsNotNone(source_snapshot)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = warehouse.AnalyticsWarehouse(root)
            manifest = source_snapshot.persist_source_snapshot(
                root,
                store,
                source="gsc",
                run_id="2026-07-12T00:30:00Z",
                dataset="search_analytics",
                raw_rows=[{"record_type": "detail", "date": "2026-07-11", "clicks": 1}],
                daily_metrics=[],
            )
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["failure_reason"], "empty_daily_metrics")
            self.assertEqual(store.source_complete_dates("gsc"), set())

    def test_snapshot_writer_keeps_complete_non_shopify_zero_days_valid(self) -> None:
        self.assertIsNotNone(source_snapshot)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = warehouse.AnalyticsWarehouse(root)
            manifest = source_snapshot.persist_source_snapshot(
                root,
                store,
                source="gsc",
                run_id="2026-07-12T00:30:00Z",
                dataset="search_analytics",
                raw_rows=[],
                daily_metrics=[
                    {"date": "2026-07-10", "seo_clicks": 0, "seo_impressions": 0},
                    {"date": "2026-07-11", "seo_clicks": 0, "seo_impressions": 0},
                ],
                expected_start_date="2026-07-10",
                expected_end_date="2026-07-11",
            )
            self.assertEqual(manifest["status"], "valid_zero")
            self.assertEqual(store.source_complete_dates("gsc"), {"2026-07-10", "2026-07-11"})

    def test_snapshot_writer_accepts_successful_gsc_rollup_with_omitted_zero_day(self) -> None:
        self.assertIsNotNone(source_metrics)
        self.assertIsNotNone(source_snapshot)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = warehouse.AnalyticsWarehouse(root)
            daily_metrics = source_metrics.rollup_source_rows(
                "gsc",
                [{"date": "2026-07-11", "clicks": 1, "impressions": 10}],
                start_date="2026-07-10",
                end_date="2026-07-11",
            )
            manifest = source_snapshot.persist_source_snapshot(
                root,
                store,
                source="gsc",
                run_id="2026-07-12T00:30:00Z",
                dataset="search_analytics",
                raw_rows=[{"date": "2026-07-11", "clicks": 1, "impressions": 10}],
                daily_metrics=daily_metrics,
                expected_start_date="2026-07-10",
                expected_end_date="2026-07-11",
            )
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(store.source_complete_dates("gsc"), {"2026-07-10", "2026-07-11"})

    def test_snapshot_writer_fails_closed_on_incomplete_requested_date_coverage(self) -> None:
        self.assertIsNotNone(source_snapshot)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = warehouse.AnalyticsWarehouse(root)
            manifest = source_snapshot.persist_source_snapshot(
                root,
                store,
                source="gsc",
                run_id="2026-07-12T00:30:00Z",
                dataset="search_analytics",
                raw_rows=[{"date": "2026-07-11", "clicks": 1}],
                daily_metrics=[{"date": "2026-07-11", "seo_clicks": 1, "seo_impressions": 10}],
                expected_start_date="2026-07-10",
                expected_end_date="2026-07-11",
            )
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["failure_reason"], "incomplete_daily_coverage")
            self.assertEqual(manifest["expected_date_range"], ["2026-07-10", "2026-07-11"])
            self.assertEqual(store.source_complete_dates("gsc"), set())

    def test_snapshot_writer_fails_closed_when_shopify_raw_schema_is_incomplete(self) -> None:
        self.assertIsNotNone(source_snapshot)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = warehouse.AnalyticsWarehouse(root)
            manifest = source_snapshot.persist_source_snapshot(
                root,
                store,
                source="shopify",
                run_id="2026-07-12T00:30:00Z",
                dataset="orders",
                raw_rows=[{"date": "2026-07-11", "total_price": 100.0}],
                daily_metrics=[
                    {
                        "date": "2026-07-11",
                        "orders": 1,
                        "revenue": 100.0,
                        "online_store_orders": 1,
                        "online_store_revenue": 100.0,
                        "offsite_orders": 0,
                        "offsite_revenue": 0.0,
                    }
                ],
            )
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["failure_reason"], "shopify_raw_schema_mismatch")
            self.assertEqual(store.source_complete_dates("shopify"), set())

    def test_snapshot_writer_fails_closed_when_shopify_daily_totals_do_not_reconcile(self) -> None:
        self.assertIsNotNone(source_snapshot)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = warehouse.AnalyticsWarehouse(root)
            manifest = source_snapshot.persist_source_snapshot(
                root,
                store,
                source="shopify",
                run_id="2026-07-12T00:30:00Z",
                dataset="orders",
                raw_rows=[
                    {
                        "date": "2026-07-11",
                        "total_price": 100.0,
                        "financial_status": "PAID",
                        "test": False,
                        "cancelled_at": "",
                        "source_name": "web",
                    }
                ],
                daily_metrics=[
                    {
                        "date": "2026-07-11",
                        "orders": 1,
                        "revenue": 90.0,
                        "online_store_orders": 1,
                        "online_store_revenue": 90.0,
                        "offsite_orders": 0,
                        "offsite_revenue": 0.0,
                    }
                ],
            )
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["failure_reason"], "shopify_daily_reconciliation_mismatch")
            self.assertEqual(store.source_complete_dates("shopify"), set())


if __name__ == "__main__":
    unittest.main()
