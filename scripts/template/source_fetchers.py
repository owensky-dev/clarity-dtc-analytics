from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from source_metrics import rollup_source_rows, shopify_daily_metrics


ORDERS_QUERY = """
query Orders($first: Int!, $after: String, $query: String!) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id name createdAt displayFinancialStatus displayFulfillmentStatus sourceName landingPageUrl referrerUrl
        currentSubtotalPriceSet { shopMoney { amount currencyCode } }
        currentTotalPriceSet { shopMoney { amount currencyCode } }
        currentTotalTaxSet { shopMoney { amount currencyCode } }
      }
    }
  }
}
"""


class SourceFetchError(RuntimeError):
    pass


class HttpJsonResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body


def _money(node: dict[str, Any], field: str) -> float:
    try:
        return float(node.get(field, {}).get("shopMoney", {}).get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def shopify_order_record(node: dict[str, Any], *, report_timezone: str) -> dict[str, Any]:
    """Convert a Shopify GraphQL order node into a timezone-aware store fact."""
    created_at = str(node.get("createdAt", ""))
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    shop_money = node.get("currentTotalPriceSet", {}).get("shopMoney", {})
    return {
        "created_at": created_at,
        "date": created.astimezone(ZoneInfo(report_timezone)).date().isoformat(),
        "order_id": node.get("id", ""),
        "order_name": node.get("name", ""),
        "currency": shop_money.get("currencyCode", ""),
        "subtotal_price": _money(node, "currentSubtotalPriceSet"),
        "total_price": _money(node, "currentTotalPriceSet"),
        "total_tax": _money(node, "currentTotalTaxSet"),
        "financial_status": node.get("displayFinancialStatus", ""),
        "fulfillment_status": node.get("displayFulfillmentStatus", ""),
        "source_name": node.get("sourceName", ""),
        "landing_site": node.get("landingPageUrl", ""),
        "referring_site": node.get("referrerUrl", ""),
    }


def _shopify_endpoint(shop_domain: str, api_version: str) -> str:
    domain = shop_domain.replace("https://", "").replace("http://", "").strip("/")
    return f"https://{domain}/admin/api/{api_version}/graphql.json"


def _shopify_transport(url: str, headers: dict[str, str], payload: dict[str, Any]) -> HttpJsonResponse:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            return HttpJsonResponse(int(response.status), response.read())
    except Exception as error:  # HTTPError and network failures expose different APIs.
        return HttpJsonResponse(int(getattr(error, "code", 599)), str(error).encode("utf-8", errors="replace"))


def fetch_shopify_orders(
    *,
    shop_domain: str,
    access_token: str,
    api_version: str,
    start_date: str,
    end_date: str,
    report_timezone: str,
    transport: Any | None = None,
) -> list[dict[str, Any]]:
    """Fetch Shopify orders and convert their dates in the configured report timezone."""
    transport = transport or _shopify_transport
    headers = {"X-Shopify-Access-Token": access_token, "Content-Type": "application/json"}
    variables: dict[str, Any] = {
        "first": 100,
        "after": None,
        "query": f"created_at:>={start_date} created_at:<={end_date}",
    }
    rows: list[dict[str, Any]] = []
    while True:
        response = transport(
            _shopify_endpoint(shop_domain, api_version),
            headers,
            {"query": ORDERS_QUERY, "variables": variables},
        )
        if response.status != 200:
            raise SourceFetchError(f"Shopify GraphQL returned HTTP {response.status}")
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SourceFetchError("Shopify GraphQL returned invalid JSON") from error
        if payload.get("errors"):
            raise SourceFetchError(f"Shopify GraphQL errors: {payload['errors']}")
        orders = payload.get("data", {}).get("orders", {})
        for edge in orders.get("edges", []):
            node = edge.get("node", {})
            rows.append(shopify_order_record(node, report_timezone=report_timezone))
        page_info = orders.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        variables["after"] = page_info.get("endCursor")
    return rows


def _require(settings: dict[str, str], *keys: str) -> None:
    missing = [key for key in keys if not settings.get(key)]
    if missing:
        raise SourceFetchError(f"Missing required source configuration: {', '.join(missing)}")


def _dataset(name: str, raw_rows: list[dict[str, Any]], daily_metrics: list[dict[str, Any]]) -> Any:
    # Imported lazily to avoid a module cycle with the daily runner.
    from daily_runner import SourceDataset

    return SourceDataset(dataset=name, raw_rows=raw_rows, daily_metrics=daily_metrics)


def fetch_shopify_dataset(settings: dict[str, str], start_date: str, end_date: str) -> Any:
    _require(settings, "SHOPIFY_SHOP_DOMAIN", "SHOPIFY_ADMIN_ACCESS_TOKEN", "REPORT_TIMEZONE")
    rows = fetch_shopify_orders(
        shop_domain=settings["SHOPIFY_SHOP_DOMAIN"],
        access_token=settings["SHOPIFY_ADMIN_ACCESS_TOKEN"],
        api_version=settings.get("SHOPIFY_API_VERSION", "2025-10"),
        start_date=start_date,
        end_date=end_date,
        report_timezone=settings["REPORT_TIMEZONE"],
    )
    return _dataset("orders", rows, shopify_daily_metrics(rows, start_date=start_date, end_date=end_date))


def _ga4_rows(settings: dict[str, str], start_date: str, end_date: str) -> list[dict[str, Any]]:
    _require(settings, "GOOGLE_APPLICATION_CREDENTIALS", "GA4_PROPERTY_ID")
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
        from google.oauth2 import service_account
    except ImportError as error:
        raise SourceFetchError("Install google-analytics-data and google-auth for GA4 collection.") from error
    credentials = service_account.Credentials.from_service_account_file(settings["GOOGLE_APPLICATION_CREDENTIALS"])
    client = BetaAnalyticsDataClient(credentials=credentials)
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = client.run_report(
            RunReportRequest(
                property=f"properties/{settings['GA4_PROPERTY_ID']}",
                dimensions=[Dimension(name="date"), Dimension(name="sessionDefaultChannelGroup")],
                metrics=[Metric(name=name) for name in ("sessions", "engagedSessions", "conversions", "ecommercePurchases", "totalRevenue")],
                date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
                limit=100000,
                offset=offset,
            )
        )
        if not response.rows:
            break
        for row in response.rows:
            record = {
                "date": row.dimension_values[0].value,
                "sessionDefaultChannelGroup": row.dimension_values[1].value,
            }
            record.update(
                {
                    key: float(value.value or 0)
                    for key, value in zip(("sessions", "engagedSessions", "conversions", "ecommercePurchases", "totalRevenue"), row.metric_values)
                }
            )
            rows.append(record)
        if len(response.rows) < 100000:
            break
        offset += 100000
    return rows


def fetch_ga4_dataset(settings: dict[str, str], start_date: str, end_date: str) -> Any:
    rows = _ga4_rows(settings, start_date, end_date)
    return _dataset("channel", rows, rollup_source_rows("ga4", rows))


def _gsc_query_rows(
    service: Any, *, site_url: str, start_date: str, end_date: str, dimensions: list[str]
) -> list[dict[str, Any]]:
    """Fetch a complete paged GSC result for diagnostic dimensions."""
    rows: list[dict[str, Any]] = []
    start_row = 0
    while True:
        result = service.searchanalytics().query(
            siteUrl=site_url,
            body={"startDate": start_date, "endDate": end_date, "dimensions": dimensions, "rowLimit": 25000, "startRow": start_row},
        ).execute()
        batch = result.get("rows", [])
        if not batch:
            break
        for item in batch:
            keys = item.get("keys", [])
            rows.append(
                {
                    **{dimension: keys[index] if index < len(keys) else "" for index, dimension in enumerate(dimensions)},
                    "clicks": item.get("clicks", 0),
                    "impressions": item.get("impressions", 0),
                    "ctr": item.get("ctr", 0),
                    "position": item.get("position", 0),
                }
            )
        if len(batch) < 25000:
            break
        start_row += 25000
    return rows


def _gsc_service(settings: dict[str, str]) -> Any:
    _require(settings, "GOOGLE_APPLICATION_CREDENTIALS", "GSC_SITE_URL")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as error:
        raise SourceFetchError("Install google-api-python-client and google-auth for GSC collection.") from error
    credentials = service_account.Credentials.from_service_account_file(
        settings["GOOGLE_APPLICATION_CREDENTIALS"], scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
    )
    return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)


def _gsc_rows(settings: dict[str, str], start_date: str, end_date: str) -> list[dict[str, Any]]:
    service = _gsc_service(settings)
    return _gsc_query_rows(
        service,
        site_url=settings["GSC_SITE_URL"],
        start_date=start_date,
        end_date=end_date,
        dimensions=["date", "page", "query", "country", "device"],
    )


def _gsc_daily_rows(settings: dict[str, str], start_date: str, end_date: str) -> list[dict[str, Any]]:
    """Use date-only GSC totals as the report source; high-cardinality rows are diagnostics only."""
    service = _gsc_service(settings)
    return _gsc_query_rows(
        service,
        site_url=settings["GSC_SITE_URL"],
        start_date=start_date,
        end_date=end_date,
        dimensions=["date"],
    )


def fetch_gsc_dataset(settings: dict[str, str], start_date: str, end_date: str) -> Any:
    detail_rows = _gsc_rows(settings, start_date, end_date)
    daily_rows = _gsc_daily_rows(settings, start_date, end_date)
    raw_rows = [{"record_type": "detail", **row} for row in detail_rows] + [
        {"record_type": "daily_total", **row} for row in daily_rows
    ]
    return _dataset("search_analytics", raw_rows, rollup_source_rows("gsc", daily_rows))


def _ads_rows(settings: dict[str, str], start_date: str, end_date: str) -> list[dict[str, Any]]:
    _require(
        settings,
        "GOOGLE_ADS_CUSTOMER_ID",
        "GOOGLE_ADS_DEVELOPER_TOKEN",
        "GOOGLE_ADS_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET",
        "GOOGLE_ADS_REFRESH_TOKEN",
    )
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError as error:
        raise SourceFetchError("Install google-ads for Google Ads collection.") from error
    config = {
        "developer_token": settings["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": settings["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": settings["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": settings["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": settings.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID") or settings["GOOGLE_ADS_CUSTOMER_ID"],
        "use_proto_plus": True,
    }
    client = GoogleAdsClient.load_from_dict(config)
    query = f"""
      SELECT segments.date, campaign.id, campaign.name, ad_group.id, ad_group.name,
        metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions, metrics.conversions_value
      FROM ad_group
      WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
      ORDER BY segments.date, campaign.id, ad_group.id
    """
    service = client.get_service("GoogleAdsService")
    customer_id = settings["GOOGLE_ADS_CUSTOMER_ID"].replace("-", "")
    rows: list[dict[str, Any]] = []
    for batch in service.search_stream(customer_id=customer_id, query=query):
        for item in batch.results:
            rows.append(
                {
                    "date": item.segments.date,
                    "campaign_id": item.campaign.id,
                    "campaign_name": item.campaign.name,
                    "ad_group_id": item.ad_group.id,
                    "ad_group_name": item.ad_group.name,
                    "impressions": item.metrics.impressions,
                    "clicks": item.metrics.clicks,
                    "cost": item.metrics.cost_micros / 1_000_000,
                    "conversions": float(item.metrics.conversions),
                    "conversion_value": float(item.metrics.conversions_value),
                }
            )
    return rows


def fetch_google_ads_dataset(settings: dict[str, str], start_date: str, end_date: str) -> Any:
    rows = _ads_rows(settings, start_date, end_date)
    return _dataset("ad_group_performance", rows, rollup_source_rows("google_ads", rows))


def default_source_fetchers() -> dict[str, Callable[[dict[str, str], str, str], Any]]:
    return {
        "ga4": fetch_ga4_dataset,
        "gsc": fetch_gsc_dataset,
        "google_ads": fetch_google_ads_dataset,
        "shopify": fetch_shopify_dataset,
    }
