from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

try:
    import clarity_export
    import warehouse
except ModuleNotFoundError:
    clarity_export = None
    warehouse = None


class WarehouseTests(unittest.TestCase):
    def test_warehouse_persists_long_rows_and_parquet_snapshot(self) -> None:
        self.assertIsNotNone(warehouse)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parsed = clarity_export.parse_clarity_payload(
                [
                    {
                        "metricName": "Traffic",
                        "information": [
                            {
                                "Url": "https://shop.test/products/a",
                                "Device": "Mobile",
                                "Channel": "Direct",
                                "totalSessionCount": "12",
                            }
                        ],
                    }
                ],
                query_pack="url_device_channel",
                snapshot_id="2026-07-12T00:30:00Z",
            )
            store = warehouse.AnalyticsWarehouse(root)
            store.persist_clarity_snapshot(
                {
                    "snapshot_id": "2026-07-12T00:30:00Z",
                    "query_pack": "url_device_channel",
                    "fetched_at_utc": "2026-07-12T00:30:10Z",
                    "schema_mismatch": False,
                    "row_count": 1,
                },
                parsed,
            )
            self.assertEqual(store.count_rows("clarity_metric_rows"), 1)
            self.assertEqual(store.count_rows("clarity_snapshots"), 1)
            self.assertTrue(
                (root / "data" / "staged" / "clarity" / "snapshot_id=2026-07-12T00-30-00Z" / "query_pack=url_device_channel" / "metric_rows.parquet").is_file()
            )

    def test_warehouse_keeps_each_query_pack_parquet(self) -> None:
        self.assertIsNotNone(warehouse)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = warehouse.AnalyticsWarehouse(root)
            for query_pack in ("overall", "url_device_channel"):
                parsed = clarity_export.parse_clarity_payload(
                    [{"metricName": "Traffic", "information": [{"totalSessionCount": "1"}]}],
                    query_pack=query_pack,
                    snapshot_id="2026-07-12T00:30:00Z",
                )
                store.persist_clarity_snapshot(
                    {"snapshot_id": "2026-07-12T00:30:00Z", "query_pack": query_pack, "fetched_at_utc": "2026-07-12T00:30:00Z", "schema_mismatch": False, "row_count": 1},
                    parsed,
                )
            stage = root / "data" / "staged" / "clarity" / "snapshot_id=2026-07-12T00-30-00Z"
            self.assertTrue((stage / "query_pack=overall" / "metric_rows.parquet").is_file())
            self.assertTrue((stage / "query_pack=url_device_channel" / "metric_rows.parquet").is_file())

    def test_warehouse_treats_zero_order_shopify_day_as_complete_coverage(self) -> None:
        self.assertIsNotNone(warehouse)
        with tempfile.TemporaryDirectory() as directory:
            store = warehouse.AnalyticsWarehouse(Path(directory))
            store.persist_source_daily_metrics(
                "shopify",
                "2026-07-12T00:30:00Z",
                [
                    {"date": "2026-07-11", "orders": 0, "revenue": 0.0},
                    {"date": "2026-07-12", "orders": 2, "revenue": 180.0},
                ],
            )
            self.assertEqual(store.source_complete_dates("shopify"), {"2026-07-11", "2026-07-12"})


if __name__ == "__main__":
    unittest.main()
