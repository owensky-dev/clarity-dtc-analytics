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


def shopify_daily_metrics(
    order_rows: list[dict[str, Any]], *, start_date: str, end_date: str
) -> list[dict[str, Any]]:
    """Return a complete date series so zero sales do not look like missing collection."""
    grouped: dict[str, dict[str, float]] = defaultdict(lambda: {"orders": 0, "revenue": 0.0})
    for row in order_rows:
        date_value = str(row.get("date") or row.get("created_at", ""))[:10]
        if not date_value:
            continue
        grouped[date_value]["orders"] += 1
        grouped[date_value]["revenue"] += _number(row.get("total_price", row.get("revenue")))
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    return [
        {
            "date": current.isoformat(),
            "orders": int(grouped[current.isoformat()]["orders"]),
            "revenue": round(grouped[current.isoformat()]["revenue"], 2),
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
