from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

try:
    import source_fetchers
except ModuleNotFoundError:
    source_fetchers = None


class SourceFetcherTests(unittest.TestCase):
    def test_shopify_order_record_uses_explicit_report_timezone(self) -> None:
        self.assertIsNotNone(source_fetchers)
        record = source_fetchers.shopify_order_record(
            {
                "id": "gid://shopify/Order/1",
                "name": "#1001",
                "createdAt": "2026-07-12T01:15:00Z",
                "displayFinancialStatus": "PAID",
                "currentTotalPriceSet": {"shopMoney": {"amount": "125.50", "currencyCode": "USD"}},
            },
            report_timezone="America/Los_Angeles",
        )
        self.assertEqual(record["date"], "2026-07-11")
        self.assertEqual(record["order_id"], "gid://shopify/Order/1")
        self.assertEqual(record["total_price"], 125.5)

    def test_shopify_fetcher_pages_graphql_orders(self) -> None:
        self.assertIsNotNone(source_fetchers)
        requested_after: list[str | None] = []

        def transport(url: str, headers: dict[str, str], payload: dict) -> source_fetchers.HttpJsonResponse:
            requested_after.append(payload["variables"]["after"])
            node = {
                "id": f"gid://shopify/Order/{len(requested_after)}",
                "name": f"#{len(requested_after)}",
                "createdAt": "2026-07-12T01:15:00Z",
                "currentTotalPriceSet": {"shopMoney": {"amount": "10.00", "currencyCode": "USD"}},
            }
            has_next = len(requested_after) == 1
            body = {"data": {"orders": {"pageInfo": {"hasNextPage": has_next, "endCursor": "next" if has_next else None}, "edges": [{"node": node}]}}}
            return source_fetchers.HttpJsonResponse(200, json.dumps(body).encode("utf-8"))

        rows = source_fetchers.fetch_shopify_orders(
            shop_domain="shop.test",
            access_token="token",
            api_version="2025-10",
            start_date="2026-07-11",
            end_date="2026-07-12",
            report_timezone="America/Los_Angeles",
            transport=transport,
        )
        self.assertEqual(requested_after, [None, "next"])
        self.assertEqual([row["order_id"] for row in rows], ["gid://shopify/Order/1", "gid://shopify/Order/2"])

    def test_default_fetcher_registry_covers_all_core_sources(self) -> None:
        self.assertIsNotNone(source_fetchers)
        self.assertEqual(
            set(source_fetchers.default_source_fetchers()),
            {"ga4", "gsc", "google_ads", "shopify"},
        )

    def test_ga4_dataset_keeps_channel_and_dated_funnel_rows_separate(self) -> None:
        self.assertIsNotNone(source_fetchers)
        channel_rows = [{"date": "20260712", "sessionDefaultChannelGroup": "Organic Search", "sessions": 20}]
        event_rows = [
            {"date": "20260712", "landingPagePlusQueryString": "/p?access_token=secret", "eventName": "add_to_cart", "eventCount": 4},
            {"date": "20260712", "landingPagePlusQueryString": "/p", "eventName": "begin_checkout", "eventCount": 2},
        ]
        with patch.object(source_fetchers, "_ga4_rows", return_value=(channel_rows, event_rows)):
            dataset = source_fetchers.fetch_ga4_dataset({}, "2026-07-12", "2026-07-12")
        self.assertEqual(dataset.dataset, "channel_and_funnel")
        self.assertEqual(dataset.raw_rows[0]["record_type"], "channel")
        self.assertEqual(dataset.raw_rows[-1]["record_type"], "funnel_event")
        self.assertEqual(dataset.raw_rows[1]["landingPagePlusQueryString"], "/p")
        self.assertEqual(dataset.daily_metrics[0]["sessions"], 20.0)
        self.assertEqual(dataset.daily_metrics[0]["add_to_cart"], 4.0)
        self.assertEqual(dataset.daily_metrics[0]["begin_checkout"], 2.0)

    def test_gsc_daily_query_uses_date_only_for_report_totals(self) -> None:
        self.assertIsNotNone(source_fetchers)
        calls: list[dict] = []

        class Request:
            def execute(self):
                return {"rows": [{"keys": ["2026-07-12"], "clicks": 5, "impressions": 100}]}

        class SearchAnalytics:
            def query(self, **kwargs):
                calls.append(kwargs["body"])
                return Request()

        class Service:
            def searchanalytics(self):
                return SearchAnalytics()

        rows = source_fetchers._gsc_query_rows(
            Service(), site_url="https://shop.test/", start_date="2026-07-12", end_date="2026-07-12", dimensions=["date"]
        )
        self.assertEqual(calls[0]["dimensions"], ["date"])
        self.assertEqual(rows[0]["clicks"], 5)


if __name__ == "__main__":
    unittest.main()
