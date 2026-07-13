from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from warehouse import AnalyticsWarehouse


def _safe_run_id(run_id: str) -> str:
    return run_id.replace(":", "-")


def persist_source_snapshot(
    project_root: Path,
    store: AnalyticsWarehouse,
    *,
    source: str,
    run_id: str,
    dataset: str,
    raw_rows: list[dict[str, Any]],
    daily_metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    """Persist raw source data and update date-level warehouse coverage."""
    output_dir = project_root / "data" / "raw" / source / f"run_id={_safe_run_id(run_id)}"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / f"{dataset}.json"
    serialized = json.dumps(raw_rows, ensure_ascii=False, indent=2, sort_keys=True)
    raw_path.write_text(serialized, encoding="utf-8")
    dates = sorted(str(row["date"]) for row in daily_metrics if row.get("date"))
    status = "valid_zero" if daily_metrics and all(
        all(float(value or 0) == 0 for key, value in row.items() if key != "date")
        for row in daily_metrics
    ) else "complete"
    manifest = {
        "source": source,
        "run_id": run_id,
        "dataset": dataset,
        "status": status,
        "raw_row_count": len(raw_rows),
        "daily_metric_count": len(daily_metrics),
        "date_range": [dates[0], dates[-1]] if dates else [],
        "raw_path": str(raw_path),
        "response_hash": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
    }
    (output_dir / f"{dataset}.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    store.persist_source_daily_metrics(source, run_id, daily_metrics, status=status)
    return manifest
