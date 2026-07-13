from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

try:
    import clarity_export
    import daily_report
    import warehouse
except ModuleNotFoundError:
    clarity_export = None
    daily_report = None
    warehouse = None


class DailyReportTests(unittest.TestCase):
    def test_daily_alert_outputs_fact_inference_and_validation_action(self) -> None:
        self.assertIsNotNone(daily_report)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = warehouse.AnalyticsWarehouse(root)
            parsed = clarity_export.parse_clarity_payload(
                [
                    {"metricName": "Traffic", "information": [{"Url": "https://shop.test/p", "Device": "Mobile", "Channel": "Direct", "totalSessionCount": "100"}]},
                    {"metricName": "ErrorClickCount", "information": [{"Url": "https://shop.test/p", "Device": "Mobile", "Channel": "Direct", "subTotal": "20"}]},
                ],
                query_pack="url_device_channel",
                snapshot_id="2026-07-12T00:30:00Z",
            )
            store.persist_clarity_snapshot(
                {"snapshot_id": "2026-07-12T00:30:00Z", "query_pack": "url_device_channel", "fetched_at_utc": "2026-07-12T00:30:00Z", "schema_mismatch": False, "row_count": 2},
                parsed,
            )
            result = daily_report.generate_daily_alert(store, root / "outputs", "2026-07-12")
            payload = json.loads(result.json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["anomalies"][0]["fact"], "错误点击率为 20.00%，超过 10.00% 的严重阈值。")
            self.assertIn("推测", payload["anomalies"][0])
            self.assertIn("验证动作", payload["anomalies"][0])
            self.assertTrue(result.markdown_path.is_file())


if __name__ == "__main__":
    unittest.main()
