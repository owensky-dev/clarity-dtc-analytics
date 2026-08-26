from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _iso_date(value: Any) -> str:
    """Normalize GA4's YYYYMMDD date dimension to the warehouse ISO contract."""
    text = str(value or "")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


SHOPIFY_ORDER_FIELDS = {
    "date",
    "total_price",
    "financial_status",
    "test",
    "cancelled_at",
    "source_name",
}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _is_business_order(row: dict[str, Any]) -> bool:
    missing = sorted(SHOPIFY_ORDER_FIELDS.difference(row))
    if missing:
        raise ValueError(f"Shopify order row is missing required fields: {', '.join(missing)}")
    return (
        str(row.get("financial_status") or "").upper() == "PAID"
        and not _truthy(row.get("test"))
        and not str(row.get("cancelled_at") or "").strip()
    )


def shopify_daily_metrics(
    order_rows: list[dict[str, Any]], *, start_date: str, end_date: str
) -> list[dict[str, Any]]:
    """Return paid, non-test, non-cancelled business and channel totals by report date."""
    grouped: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "orders": 0,
            "revenue": 0.0,
            "online_store_orders": 0,
            "online_store_revenue": 0.0,
            "offsite_orders": 0,
            "offsite_revenue": 0.0,
        }
    )
    for row in order_rows:
        if not _is_business_order(row):
            continue
        date_value = str(row["date"])
        amount = _number(row["total_price"])
        grouped[date_value]["orders"] += 1
        grouped[date_value]["revenue"] += amount
        if str(row["source_name"] or "").lower() == "web":
            grouped[date_value]["online_store_orders"] += 1
            grouped[date_value]["online_store_revenue"] += amount
        else:
            grouped[date_value]["offsite_orders"] += 1
            grouped[date_value]["offsite_revenue"] += amount
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        raise ValueError("Shopify start_date must not be after end_date")
    return [
        {
            "date": current.isoformat(),
            "orders": int(grouped[current.isoformat()]["orders"]),
            "revenue": round(grouped[current.isoformat()]["revenue"], 2),
            "online_store_orders": int(grouped[current.isoformat()]["online_store_orders"]),
            "online_store_revenue": round(grouped[current.isoformat()]["online_store_revenue"], 2),
            "offsite_orders": int(grouped[current.isoformat()]["offsite_orders"]),
            "offsite_revenue": round(grouped[current.isoformat()]["offsite_revenue"], 2),
        }
        for current in (start + timedelta(days=offset) for offset in range((end - start).days + 1))
    ]


SOURCE_METRIC_MAP = {
    "ga4": {
        "sessions": "sessions",
        "engaged_sessions": "engagedSessions",
        "conversions": "conversions",
        "ecommerce_purchases": "ecommercePurchases",
        "ga4_revenue": "totalRevenue",
    },
    "google_ads": {
        "ad_clicks": "clicks",
        "ad_spend": "cost",
        "ad_conversions": "conversions",
        "ad_conversion_value": "conversion_value",
    },
    "gsc": {
        "seo_clicks": "clicks",
        "seo_impressions": "impressions",
    },
}


def rollup_source_rows(source: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate API rows by source date without conflating source metric meanings."""
    if source not in SOURCE_METRIC_MAP:
        raise ValueError(f"Unsupported source rollup: {source}")
    mapping = SOURCE_METRIC_MAP[source]
    grouped: dict[str, dict[str, float]] = {}
    for row in rows:
        date_value = _iso_date(row.get("date", ""))
        if not date_value:
            continue
        aggregate = grouped.setdefault(date_value, {target: 0.0 for target in mapping})
        for target, source_key in mapping.items():
            aggregate[target] += _number(row.get(source_key))
    return [{"date": date_value, **grouped[date_value]} for date_value in sorted(grouped)]


def rollup_ga4_rows(
    channel_rows: list[dict[str, Any]], event_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge dated GA4 funnel events into channel-derived daily coverage."""
    daily = rollup_source_rows("ga4", channel_rows)
    by_date = {row["date"]: row for row in daily}
    for row in daily:
        row["add_to_cart"] = 0.0
        row["begin_checkout"] = 0.0
    for event in event_rows:
        date_value = _iso_date(event.get("date", ""))
        event_name = str(event.get("eventName", ""))
        if date_value not in by_date or event_name not in {"add_to_cart", "begin_checkout"}:
            continue
        by_date[date_value][event_name] += _number(event.get("eventCount"))
    return [by_date[date_value] for date_value in sorted(by_date)]
