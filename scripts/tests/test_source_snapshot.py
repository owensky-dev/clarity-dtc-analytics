from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

try:
    import source_snapshot
    import warehouse
except ModuleNotFoundError:
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
                daily_metrics=[{"date": "2026-07-11", "orders": 0, "revenue": 0.0}],
            )
            self.assertEqual(manifest["status"], "valid_zero")
            self.assertEqual(manifest["date_range"], ["2026-07-11", "2026-07-11"])
            raw_path = root / "data" / "raw" / "shopify" / "run_id=2026-07-12T00-30-00Z" / "orders.json"
            self.assertEqual(json.loads(raw_path.read_text(encoding="utf-8")), [])


if __name__ == "__main__":
    unittest.main()
