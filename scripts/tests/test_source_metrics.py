from __future__ import annotations

import sys
import unittest
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

try:
    import source_metrics
except ModuleNotFoundError:
    source_metrics = None


class SourceMetricsTests(unittest.TestCase):
    def test_shopify_rollup_preserves_zero_order_days(self) -> None:
        self.assertIsNotNone(source_metrics)
        rows = source_metrics.shopify_daily_metrics(
            [{"date": "2026-07-12", "total_price": "125.50", "order_id": "gid://shopify/Order/1"}],
            start_date="2026-07-11",
            end_date="2026-07-12",
        )
        self.assertEqual(
            rows,
            [
                {"date": "2026-07-11", "orders": 0, "revenue": 0.0},
                {"date": "2026-07-12", "orders": 1, "revenue": 125.5},
            ],
        )

    def test_ga4_ads_and_gsc_rollups_keep_source_specific_metrics(self) -> None:
        self.assertIsNotNone(source_metrics)
        ga4 = source_metrics.rollup_source_rows(
            "ga4",
            [
                {"date": "2026-07-12", "sessions": "10", "engagedSessions": "6", "conversions": "1", "ecommercePurchases": "1", "totalRevenue": "40"},
                {"date": "2026-07-12", "sessions": "8", "engagedSessions": "5", "conversions": "0", "ecommercePurchases": "0", "totalRevenue": "0"},
            ],
        )
        ads = source_metrics.rollup_source_rows(
            "google_ads",
            [{"date": "2026-07-12", "clicks": 12, "cost": 8.5, "conversions": 0, "conversion_value": 0}],
        )
        gsc = source_metrics.rollup_source_rows(
            "gsc",
            [{"date": "2026-07-12", "clicks": 3, "impressions": 100}],
        )
        self.assertEqual(ga4, [{"date": "2026-07-12", "sessions": 18.0, "engaged_sessions": 11.0, "conversions": 1.0, "ecommerce_purchases": 1.0, "ga4_revenue": 40.0}])
        self.assertEqual(ads, [{"date": "2026-07-12", "ad_clicks": 12.0, "ad_spend": 8.5, "ad_conversions": 0.0, "ad_conversion_value": 0.0}])
        self.assertEqual(gsc, [{"date": "2026-07-12", "seo_clicks": 3.0, "seo_impressions": 100.0}])

    def test_ga4_compact_api_dates_are_normalized_to_iso_dates(self) -> None:
        self.assertIsNotNone(source_metrics)
        rows = source_metrics.rollup_source_rows(
            "ga4",
            [{"date": "20260712", "sessions": 12}],
        )
        self.assertEqual(rows, [{"date": "2026-07-12", "sessions": 12.0, "engaged_sessions": 0.0, "conversions": 0.0, "ecommerce_purchases": 0.0, "ga4_revenue": 0.0}])

    def test_ga4_rollup_merges_dated_add_to_cart_and_checkout_events(self) -> None:
        self.assertIsNotNone(source_metrics)
        rows = source_metrics.rollup_ga4_rows(
            [
                {"date": "20260711", "sessions": 10},
                {"date": "20260712", "sessions": 20},
            ],
            [
                {"date": "20260711", "eventName": "add_to_cart", "eventCount": 3},
                {"date": "20260711", "eventName": "begin_checkout", "eventCount": 1},
                {"date": "20260712", "eventName": "add_to_cart", "eventCount": 4},
                {"date": "20260712", "eventName": "begin_checkout", "eventCount": 2},
            ],
        )
        self.assertEqual(rows[0]["add_to_cart"], 3.0)
        self.assertEqual(rows[0]["begin_checkout"], 1.0)
        self.assertEqual(rows[1]["add_to_cart"], 4.0)
        self.assertEqual(rows[1]["begin_checkout"], 2.0)


if __name__ == "__main__":
    unittest.main()
