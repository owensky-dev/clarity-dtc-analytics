from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import html
import json
from pathlib import Path
from typing import Iterable

from warehouse import AnalyticsWarehouse


REQUIRED_WEEKLY_SOURCES = ("ga4", "shopify", "google_ads", "gsc")


@dataclass(frozen=True)
class AlignedWindow:
    current_start: date
    current_end: date
    previous_start: date
    previous_end: date


class DataCoverageError(RuntimeError):
    pass


@dataclass(frozen=True)
class WeeklyReportResult:
    json_path: Path
    markdown_path: Path
    html_path: Path
    analysis_context_path: Path
    payload: dict


def _as_dates(values: Iterable[str | date]) -> set[date]:
    return {value if isinstance(value, date) else date.fromisoformat(value) for value in values}


def latest_aligned_14_day_window(source_dates: dict[str, Iterable[str | date]]) -> AlignedWindow:
    """Find the latest contiguous 14-day period covered by all four core sources."""
    missing_sources = [source for source in REQUIRED_WEEKLY_SOURCES if source not in source_dates]
    if missing_sources:
        raise DataCoverageError(f"Missing weekly source dates: {', '.join(missing_sources)}")
    dates_by_source = {
        source: _as_dates(source_dates[source]) for source in REQUIRED_WEEKLY_SOURCES
    }
    if any(not values for values in dates_by_source.values()):
        raise DataCoverageError("At least one weekly source has no complete dates.")

    end = min(max(values) for values in dates_by_source.values())
    earliest = max(min(values) for values in dates_by_source.values())
    while end - timedelta(days=13) >= earliest:
        all_days = {end - timedelta(days=offset) for offset in range(14)}
        if all(all_days.issubset(values) for values in dates_by_source.values()):
            return AlignedWindow(
                current_start=end - timedelta(days=6),
                current_end=end,
                previous_start=end - timedelta(days=13),
                previous_end=end - timedelta(days=7),
            )
        end -= timedelta(days=1)
    raise DataCoverageError("No continuous 14-day period is complete across GA4, Shopify, Google Ads, and GSC.")


def _sum(rows: list[dict], key: str) -> float:
    return sum(float(row.get(key, 0) or 0) for row in rows)


def _period_summary(store: AnalyticsWarehouse, start: date, end: date) -> dict[str, float | None]:
    start_text, end_text = start.isoformat(), end.isoformat()
    shopify = store.source_daily_metrics("shopify", start_text, end_text)
    ga4 = store.source_daily_metrics("ga4", start_text, end_text)
    ads = store.source_daily_metrics("google_ads", start_text, end_text)
    gsc = store.source_daily_metrics("gsc", start_text, end_text)
    revenue = _sum(shopify, "revenue")
    orders = _sum(shopify, "orders")
    sessions = _sum(ga4, "sessions")
    ad_spend = _sum(ads, "ad_spend")
    ad_conversions = _sum(ads, "ad_conversions")
    ad_conversion_value = _sum(ads, "ad_conversion_value")
    return {
        "revenue": revenue,
        "orders": orders,
        "sessions": sessions,
        "conversion_rate": orders / sessions if sessions else None,
        "aov": revenue / orders if orders else None,
        "ad_spend": ad_spend,
        "ad_clicks": _sum(ads, "ad_clicks"),
        "ad_conversions": ad_conversions,
        "ad_conversion_value": ad_conversion_value,
        "roas": ad_conversion_value / ad_spend if ad_spend else None,
        "cpa": ad_spend / ad_conversions if ad_conversions else None,
        "seo_clicks": _sum(gsc, "seo_clicks"),
        "seo_impressions": _sum(gsc, "seo_impressions"),
        "seo_ctr": _sum(gsc, "seo_clicks") / _sum(gsc, "seo_impressions") if _sum(gsc, "seo_impressions") else None,
    }


def _markdown(payload: dict) -> str:
    current = payload["current"]
    lines = [
        "# 独立站周度 CRO 报告",
        "",
        f"周报周期：{payload['window']['current_start']} 至 {payload['window']['current_end']}",
        f"对比周期：{payload['window']['previous_start']} 至 {payload['window']['previous_end']}（前一完整周）",
        "",
        "## 管理层摘要",
        f"- Shopify 收入：{current['revenue']:.2f}；订单：{current['orders']:.0f}。",
        f"- GA4 Sessions：{current['sessions']:.0f}；全站转化率：{(current['conversion_rate'] or 0):.2%}。",
        f"- Google Ads 花费：{current['ad_spend']:.2f}；CPA：{'n/a' if current['cpa'] is None else f'{current['cpa']:.2f}'}。",
        f"- GSC 点击：{current['seo_clicks']:.0f}；CTR：{(current['seo_ctr'] or 0):.2%}。",
        "- Clarity 行为证据需单独检查覆盖与截断风险；不将聚合行为数据表述为因果。",
        "",
        "## 数据健康",
        "- 本报告仅在 GA4、Shopify、Google Ads、GSC 均覆盖当前与上周连续 14 天时生成。",
    ]
    if payload.get("cro_candidates"):
        lines += ["", "## CRO 测试候选"]
        for item in payload["cro_candidates"]:
            lines += [f"- {item['priority']}｜{item['事实']}", f"  - 推测：{item['推测']}", f"  - 验证：{item['验证动作']}"]
    return "\n".join(lines) + "\n"


def _html_report(payload: dict) -> str:
    current = payload["current"]
    rows = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"
        for label, value in (
            ("Shopify 收入", f"{current['revenue']:.2f}"),
            ("订单", f"{current['orders']:.0f}"),
            ("GA4 Sessions", f"{current['sessions']:.0f}"),
            ("全站转化率", f"{(current['conversion_rate'] or 0):.2%}"),
            ("Google Ads CPA", "n/a" if current["cpa"] is None else f"{current['cpa']:.2f}"),
        )
    )
    candidates = "".join(
        f"<li><strong>{html.escape(item['priority'])}</strong>｜{html.escape(item['事实'])}<br><span>推测：{html.escape(item['推测'])}</span><br><span>验证：{html.escape(item['验证动作'])}</span></li>"
        for item in payload.get("cro_candidates", [])
    )
    candidate_section = f"<h2>CRO 测试候选</h2><ul>{candidates}</ul>" if candidates else ""
    return (
        "<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\">"
        "<title>独立站周度 CRO 报告</title>"
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:900px;margin:40px auto;color:#18231c}table{border-collapse:collapse;width:100%}th,td{padding:10px;border-bottom:1px solid #ddd;text-align:left}</style>"
        f"<h1>独立站周度 CRO 报告</h1><p>周报周期：{payload['window']['current_start']} 至 {payload['window']['current_end']}</p>"
        f"<p>对比周期：{payload['window']['previous_start']} 至 {payload['window']['previous_end']}（前一完整周）</p><table>{rows}</table>"
        f"{candidate_section}<p>Clarity 仅作为行为证据；请复核代表性录像或热图后再确定因果与测试方案。</p></html>"
    )


def _cro_candidates(pages: list[dict]) -> list[dict]:
    candidates = []
    for page in pages:
        rates = {
            "Error Click": page.get("error_click_rate") or 0,
            "Script Error": page.get("script_error_rate") or 0,
            "Dead Click": page.get("dead_click_rate") or 0,
            "Rage Click": page.get("rage_click_rate") or 0,
        }
        label, rate = max(rates.items(), key=lambda item: item[1])
        if rate <= 0:
            continue
        candidates.append(
            {
                "priority": "P1" if label in {"Error Click", "Script Error"} else "P2",
                "事实": f"{page['canonical_url']} 的 {page['device']} / {page['channel']} 切片有 {page['sessions']:.0f} 个会话，{label} 率为 {rate:.2%}。",
                "推测": "该页面可能存在可见但不可用的交互、脚本问题或信息理解阻力；需要人工复核，不能视为因果。",
                "验证动作": "在 Clarity 中按页面、设备和渠道筛选，查看代表性录像与点击热图，并复核前端控制台错误。",
                "证据可信度": "中" if page["sessions"] < 100 else "高",
                "核心指标": "对应摩擦率与 GA4 加购/结账率",
            }
        )
    return candidates


def generate_weekly_report(store: AnalyticsWarehouse, output_dir: Path) -> WeeklyReportResult:
    """Generate Chinese HTML, Markdown, and JSON only after strict four-source coverage passes."""
    source_dates = {source: store.source_complete_dates(source) for source in REQUIRED_WEEKLY_SOURCES}
    window = latest_aligned_14_day_window(source_dates)
    current = _period_summary(store, window.current_start, window.current_end)
    previous = _period_summary(store, window.previous_start, window.previous_end)
    friction = store.clarity_friction_summary(window.current_start.isoformat(), window.current_end.isoformat())
    clarity_pages = store.clarity_page_friction(window.current_start.isoformat(), window.current_end.isoformat())
    clarity_friction = {
        "status": "available" if friction["sessions"] else "evidence_unavailable",
        **friction,
        "dead_click_rate": friction["dead_clicks"] / friction["sessions"] if friction["sessions"] else None,
        "rage_click_rate": friction["rage_clicks"] / friction["sessions"] if friction["sessions"] else None,
        "error_click_rate": friction["error_clicks"] / friction["sessions"] if friction["sessions"] else None,
        "script_error_rate": friction["script_errors"] / friction["sessions"] if friction["sessions"] else None,
        "quickback_rate": friction["quickbacks"] / friction["sessions"] if friction["sessions"] else None,
    }
    payload = {
        "window": {
            "current_start": window.current_start.isoformat(),
            "current_end": window.current_end.isoformat(),
            "previous_start": window.previous_start.isoformat(),
            "previous_end": window.previous_end.isoformat(),
        },
        "current": current,
        "previous": previous,
        "source_coverage": {source: sorted(values) for source, values in source_dates.items()},
        "clarity_friction": clarity_friction,
        "clarity_pages": clarity_pages,
        "cro_candidates": _cro_candidates(clarity_pages),
        "analysis_context": {
            "facts_only": True,
            "instruction": "Separate observed facts, inferences, and validation actions. Do not claim causality.",
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"{window.current_start.isoformat()}_to_{window.current_end.isoformat()}"
    json_path = output_dir / f"weekly_cro_report_{suffix}.json"
    markdown_path = output_dir / f"weekly_cro_report_{suffix}.md"
    html_path = output_dir / f"weekly_cro_report_{suffix}.html"
    analysis_context_path = output_dir / f"analysis_context_{suffix}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    analysis_context_path.write_text(
        json.dumps(
            {
                "window": payload["window"],
                "current": payload["current"],
                "previous": payload["previous"],
                "clarity_friction": payload["clarity_friction"],
                "clarity_pages": payload["clarity_pages"],
                "cro_candidates": payload["cro_candidates"],
                "analysis_rules": payload["analysis_context"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    html_path.write_text(_html_report(payload), encoding="utf-8")
    return WeeklyReportResult(json_path, markdown_path, html_path, analysis_context_path, payload)
