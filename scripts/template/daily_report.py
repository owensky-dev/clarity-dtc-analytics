from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from warehouse import AnalyticsWarehouse


MIN_SESSIONS = 50
SEVERE_RATE = 0.10


@dataclass(frozen=True)
class DailyReportResult:
    json_path: Path
    markdown_path: Path
    payload: dict


def _anomaly(metric: str, label: str, summary: dict[str, float]) -> dict | None:
    sessions = summary["sessions"]
    count = summary[metric]
    rate = count / sessions if sessions else 0.0
    if sessions < MIN_SESSIONS or rate < SEVERE_RATE:
        return None
    return {
        "severity": "严重",
        "fact": f"{label}率为 {rate:.2%}，超过 {SEVERE_RATE:.2%} 的严重阈值。",
        "受影响会话": sessions,
        "指标变化": {"count": count, "rate": rate},
        "推测": "该行为可能表示用户尝试了无法完成的交互；这不是因果结论。",
        "验证动作": "在 Clarity 中使用相同页面、设备和渠道筛选条件，人工复核代表性录像与热图。",
        "证据可信度": "中",
    }


def generate_daily_alert(store: AnalyticsWarehouse, output_dir: Path, snapshot_date: str) -> DailyReportResult:
    """Write a local, evidence-first alert only for material behavior friction."""
    summary = store.clarity_friction_summary(snapshot_date, snapshot_date)
    anomalies = [
        anomaly
        for anomaly in (
            _anomaly("error_clicks", "错误点击", summary),
            _anomaly("script_errors", "脚本错误", summary),
            _anomaly("rage_clicks", "Rage Click", summary),
            _anomaly("dead_clicks", "Dead Click", summary),
            _anomaly("quickbacks", "Quick Back", summary),
        )
        if anomaly
    ]
    payload = {
        "snapshot_date": snapshot_date,
        "data_health": {
            "clarity_sessions": summary["sessions"],
            "status": "available" if summary["sessions"] else "evidence_unavailable",
        },
        "anomalies": anomalies,
        "rule": "Only observed metrics are asserted. Inferences require human review.",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"daily_alert_{snapshot_date}.json"
    markdown_path = output_dir / f"daily_alert_{snapshot_date}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# 每日 Clarity 异常提醒（{snapshot_date}）", "", "## 数据健康", f"- Clarity 行为会话：{summary['sessions']:.0f}"]
    if anomalies:
        lines += ["", "## 严重异常"]
        for item in anomalies:
            lines += [f"- 事实：{item['fact']}", f"  - 推测：{item['推测']}", f"  - 验证：{item['验证动作']}"]
    else:
        lines += ["", "未达到严重异常阈值；仍可按需人工查看 Clarity 保存分群。"]
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return DailyReportResult(json_path=json_path, markdown_path=markdown_path, payload=payload)
