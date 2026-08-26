from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

try:
    import clarity_export
    import reporting
    import warehouse
except ModuleNotFoundError:
    reporting = None
    warehouse = None


def period(start: date) -> list[str]:
    return [(start + timedelta(days=offset)).isoformat() for offset in range(14)]


def shopify_day(
    value: str,
    *,
    orders: int = 1,
    revenue: float = 100.0,
    online_store_orders: int = 1,
    online_store_revenue: float = 100.0,
    offsite_orders: int = 0,
    offsite_revenue: float = 0.0,
) -> dict:
    return {
        "date": value,
        "orders": orders,
        "revenue": revenue,
        "online_store_orders": online_store_orders,
        "online_store_revenue": online_store_revenue,
        "offsite_orders": offsite_orders,
        "offsite_revenue": offsite_revenue,
    }


class WeeklyReportTests(unittest.TestCase):
    def test_weekly_report_uses_shopify_revenue_and_four_source_window(self) -> None:
        self.assertIsNotNone(reporting)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = warehouse.AnalyticsWarehouse(root)
            dates = period(date(2026, 6, 29))
            store.persist_source_daily_metrics(
                "shopify", "run", [shopify_day(value) for value in dates]
            )
            store.persist_source_daily_metrics(
                "ga4",
                "run",
                [
                    {
                        "date": value,
                        "sessions": 20.0,
                        "add_to_cart": 4.0 if index < 7 else 6.0,
                        "begin_checkout": 2.0 if index < 7 else 3.0,
                        "ecommerce_purchases": 1.0,
                        "ga4_purchase_revenue": 100.0,
                        "ga4_total_revenue": 150.0,
                    }
                    for index, value in enumerate(dates)
                ],
            )
            store.persist_source_daily_metrics(
                "google_ads", "run", [{"date": value, "ad_spend": 5.0, "ad_clicks": 10.0, "ad_conversions": 0.0, "ad_conversion_value": 0.0} for value in dates]
            )
            store.persist_source_daily_metrics(
                "gsc", "run", [{"date": value, "seo_clicks": 3.0, "seo_impressions": 100.0} for value in dates]
            )
            result = reporting.generate_weekly_report(store, root / "outputs")
            payload = json.loads(result.json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["current"]["revenue"], 700.0)
            self.assertEqual(payload["current"]["orders"], 7.0)
            self.assertEqual(payload["current"]["conversion_rate"], 0.05)
            self.assertEqual(payload["current"]["add_to_cart"], 42.0)
            self.assertEqual(payload["previous"]["add_to_cart"], 28.0)
            self.assertEqual(payload["current"]["begin_checkout"], 21.0)
            self.assertEqual(payload["current"]["add_to_cart_rate"], 0.3)
            self.assertEqual(payload["current"]["cart_to_checkout_rate"], 0.5)
            self.assertEqual(payload["current"]["cpa"], None)
            self.assertTrue(result.html_path.is_file())
            self.assertTrue(result.markdown_path.is_file())
            self.assertTrue(result.analysis_context_path.is_file())
            current_period = "周报周期：2026-07-06 至 2026-07-12"
            comparison_period = "对比周期：2026-06-29 至 2026-07-05（前一完整周）"
            self.assertIn(current_period, result.markdown_path.read_text(encoding="utf-8"))
            self.assertIn(comparison_period, result.markdown_path.read_text(encoding="utf-8"))
            self.assertIn(current_period, result.html_path.read_text(encoding="utf-8"))
            self.assertIn(comparison_period, result.html_path.read_text(encoding="utf-8"))
            self.assertIn("GA4 加购", result.markdown_path.read_text(encoding="utf-8"))
            self.assertIn("GA4 开始结账", result.html_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["current"]["purchase_count_gap"], 0.0)
            self.assertEqual(payload["current"]["purchase_tracking_rate"], 1.0)

    def test_weekly_report_flags_shopify_vs_ga4_purchase_gap_without_repairing(self) -> None:
        self.assertIsNotNone(reporting)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = warehouse.AnalyticsWarehouse(root)
            dates = period(date(2026, 6, 29))
            store.persist_source_daily_metrics(
                "shopify",
                "run",
                [
                    shopify_day(value)
                    if index != 13
                    else shopify_day(
                        value,
                        orders=2,
                        revenue=140.0,
                        online_store_orders=1,
                        online_store_revenue=100.0,
                        offsite_orders=1,
                        offsite_revenue=40.0,
                    )
                    for index, value in enumerate(dates)
                ],
            )
            store.persist_source_daily_metrics(
                "ga4",
                "run",
                [
                    {
                        "date": value,
                        "sessions": 20.0,
                        "ecommerce_purchases": 0.0 if index == 13 else 1.0,
                        "ga4_purchase_revenue": 0.0 if index == 13 else 100.0,
                        "ga4_total_revenue": 1000.0,
                    }
                    for index, value in enumerate(dates)
                ],
            )
            store.persist_source_daily_metrics(
                "google_ads",
                "run",
                [{"date": value, "ad_spend": 1.0} for value in dates],
            )
            store.persist_source_daily_metrics(
                "gsc",
                "run",
                [{"date": value, "seo_clicks": 1.0, "seo_impressions": 10.0} for value in dates],
            )

            result = reporting.generate_weekly_report(store, root / "outputs")
            current = result.payload["current"]
            self.assertEqual(current["orders"], 8.0)
            self.assertEqual(current["revenue"], 740.0)
            self.assertEqual(current["online_store_orders"], 7.0)
            self.assertEqual(current["online_store_revenue"], 700.0)
            self.assertEqual(current["offsite_orders"], 1.0)
            self.assertEqual(current["offsite_revenue"], 40.0)
            self.assertEqual(current["conversion_rate"], 0.05)
            self.assertEqual(current["ga4_purchases"], 6.0)
            self.assertEqual(current["ga4_purchase_revenue"], 600.0)
            self.assertEqual(current["ga4_total_revenue"], 7000.0)
            self.assertEqual(current["purchase_count_gap"], 1.0)
            self.assertEqual(current["purchase_revenue_gap"], 100.0)
            self.assertEqual(current["purchase_tracking_rate"], 6 / 7)
            self.assertEqual(current["purchase_integrity_status"], "high_risk")

            markdown = result.markdown_path.read_text(encoding="utf-8")
            html = result.html_path.read_text(encoding="utf-8")
            self.assertIn("数据风险：Shopify Online Store 7 单，GA4 purchase 6 单", markdown)
            self.assertIn("站外 1 单 / 40.00 单列", markdown)
            self.assertIn("BigQuery transaction_id", markdown)
            self.assertIn("本报告不自动补发", markdown)
            self.assertIn("Online Store vs GA4 purchase", html)
            self.assertIn("Online Store 转化率", html)

    def test_weekly_report_adds_clarity_friction_as_behavior_evidence(self) -> None:
        self.assertIsNotNone(reporting)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = warehouse.AnalyticsWarehouse(root)
            dates = period(date(2026, 6, 29))
            for source, rows in {
                "shopify": [shopify_day(value) for value in dates],
                "ga4": [{"date": value, "sessions": 20.0} for value in dates],
                "google_ads": [{"date": value, "ad_spend": 1.0, "ad_clicks": 1.0, "ad_conversions": 0.0, "ad_conversion_value": 0.0} for value in dates],
                "gsc": [{"date": value, "seo_clicks": 1.0, "seo_impressions": 10.0} for value in dates],
            }.items():
                store.persist_source_daily_metrics(source, "run", rows)
            parsed = clarity_export.parse_clarity_payload(
                [
                    {"metricName": "Traffic", "information": [{"Url": "https://shop.test/p", "Device": "Mobile", "Channel": "Direct", "totalSessionCount": "20"}]},
                    {"metricName": "RageClickCount", "information": [{"Url": "https://shop.test/p", "Device": "Mobile", "Channel": "Direct", "subTotal": "2"}]},
                ],
                query_pack="url_device_channel",
                snapshot_id="2026-07-12T00:30:00Z",
            )
            store.persist_clarity_snapshot(
                {"snapshot_id": "2026-07-12T00:30:00Z", "query_pack": "url_device_channel", "fetched_at_utc": "2026-07-12T00:30:00Z", "schema_mismatch": False, "row_count": 2},
                parsed,
            )
            result = reporting.generate_weekly_report(store, root / "outputs")
            payload = result.payload
            self.assertEqual(payload["clarity_friction"]["status"], "available")
            self.assertEqual(payload["clarity_friction"]["rage_click_rate"], 0.1)
            self.assertEqual(payload["clarity_pages"][0]["canonical_url"], "https://shop.test/p")
            self.assertIn("事实", payload["cro_candidates"][0])
            self.assertIn("验证动作", payload["cro_candidates"][0])
            self.assertIn("https://shop.test/p", result.markdown_path.read_text(encoding="utf-8"))
            self.assertIn("https://shop.test/p", result.html_path.read_text(encoding="utf-8"))

    def test_weekly_report_fails_closed_on_legacy_shopify_daily_schema(self) -> None:
        self.assertIsNotNone(reporting)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = warehouse.AnalyticsWarehouse(root)
            dates = period(date(2026, 6, 29))
            for source, rows in {
                "shopify": [{"date": value, "orders": 1, "revenue": 100.0} for value in dates],
                "ga4": [{"date": value, "sessions": 20.0} for value in dates],
                "google_ads": [{"date": value, "ad_spend": 1.0} for value in dates],
                "gsc": [{"date": value, "seo_clicks": 1.0, "seo_impressions": 10.0} for value in dates],
            }.items():
                store.persist_source_daily_metrics(source, "run", rows)
            with self.assertRaises(reporting.DataCoverageError):
                reporting.generate_weekly_report(store, root / "outputs")


if __name__ == "__main__":
    unittest.main()
