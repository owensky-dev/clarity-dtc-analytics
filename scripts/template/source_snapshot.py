from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from source_metrics import shopify_daily_metrics
from warehouse import AnalyticsWarehouse


def _safe_run_id(run_id: str) -> str:
    return run_id.replace(":", "-")


def _shopify_reconciliation_failure(
    raw_rows: list[dict[str, Any]], daily_metrics: list[dict[str, Any]]
) -> str | None:
    required_daily_fields = {
        "date",
        "orders",
        "revenue",
        "online_store_orders",
        "online_store_revenue",
        "offsite_orders",
        "offsite_revenue",
    }
    if any(required_daily_fields.difference(row) for row in daily_metrics):
        return "shopify_daily_schema_mismatch"
    dates = [str(row["date"]) for row in daily_metrics]
    try:
        expected = shopify_daily_metrics(raw_rows, start_date=min(dates), end_date=max(dates))
    except (KeyError, TypeError, ValueError):
        return "shopify_raw_schema_mismatch"
    expected_by_date = {row["date"]: row for row in expected}
    if set(dates) != set(expected_by_date):
        return "shopify_daily_reconciliation_mismatch"
    if any(str(row.get("date") or "") not in expected_by_date for row in raw_rows):
        return "shopify_daily_reconciliation_mismatch"
    for actual in daily_metrics:
        expected_row = expected_by_date[str(actual["date"])]
        for field in required_daily_fields - {"date"}:
            if abs(float(actual[field] or 0) - float(expected_row[field] or 0)) > 0.001:
                return "shopify_daily_reconciliation_mismatch"
    return None


def persist_source_snapshot(
    project_root: Path,
    store: AnalyticsWarehouse,
    *,
    source: str,
    run_id: str,
    dataset: str,
    raw_rows: list[dict[str, Any]],
    daily_metrics: list[dict[str, Any]],
    manifest_metadata: dict[str, Any] | None = None,
    api_request_completed: bool = False,
    query_start_date: str | None = None,
    query_end_date: str | None = None,
    expected_start_date: str | None = None,
    expected_end_date: str | None = None,
) -> dict[str, Any]:
    """Persist raw source data and update date-level warehouse coverage."""
    output_dir = project_root / "data" / "raw" / source / f"run_id={_safe_run_id(run_id)}"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / f"{dataset}.json"
    serialized = json.dumps(raw_rows, ensure_ascii=False, indent=2, sort_keys=True)
    raw_path.write_text(serialized, encoding="utf-8")
    dates = sorted(str(row["date"]) for row in daily_metrics if row.get("date"))
    expected_dates: set[str] | None = None
    if expected_start_date is not None or expected_end_date is not None:
        if expected_start_date is None or expected_end_date is None:
            raise ValueError("Both expected source date bounds are required.")
        expected_start = date.fromisoformat(expected_start_date)
        expected_end = date.fromisoformat(expected_end_date)
        if expected_start > expected_end:
            raise ValueError("Expected source start date must not be after end date.")
        expected_dates = {
            (expected_start + timedelta(days=offset)).isoformat()
            for offset in range((expected_end - expected_start).days + 1)
        }
    if not daily_metrics:
        status = "failed"
        failure_reason = "empty_daily_metrics"
    elif len(dates) != len(daily_metrics):
        status = "failed"
        failure_reason = "missing_daily_date"
    elif len(set(dates)) != len(dates):
        status = "failed"
        failure_reason = "duplicate_daily_date"
    elif expected_dates is not None and set(dates) != expected_dates:
        status = "failed"
        failure_reason = "incomplete_daily_coverage"
    elif source == "shopify":
        failure_reason = _shopify_reconciliation_failure(raw_rows, daily_metrics)
        if failure_reason:
            status = "failed"
        else:
            status = "complete"
    else:
        status = "complete"
        failure_reason = None
    if status == "complete" and api_request_completed is not True:
        status = "failed"
        failure_reason = "missing_api_completion_proof"
    elif status == "complete" and (query_start_date is None or query_end_date is None):
        status = "failed"
        failure_reason = "missing_query_window"
    elif status == "complete" and not manifest_metadata:
        status = "failed"
        failure_reason = "missing_source_contract"
    elif (
        status == "complete"
        and expected_dates is not None
        and (query_start_date != expected_start_date or query_end_date != expected_end_date)
    ):
        status = "failed"
        failure_reason = "query_window_mismatch"
    if status == "complete" and all(
        all(float(value or 0) == 0 for key, value in row.items() if key != "date")
        for row in daily_metrics
    ):
        status = "valid_zero"
    manifest = {
        "source": source,
        "run_id": run_id,
        "dataset": dataset,
        "status": status,
        "raw_row_count": len(raw_rows),
        "daily_metric_count": len(daily_metrics),
        "date_range": [dates[0], dates[-1]] if dates else [],
        "expected_date_range": (
            [expected_start_date, expected_end_date] if expected_dates is not None else []
        ),
        "api_request_completed": api_request_completed,
        "query_window": (
            [query_start_date, query_end_date]
            if query_start_date is not None and query_end_date is not None
            else []
        ),
        "raw_schema": sorted({key for row in raw_rows for key in row}),
        "daily_metric_schema": sorted({key for row in daily_metrics for key in row}),
        "contract": manifest_metadata or {},
        "failure_reason": failure_reason,
        "raw_path": str(raw_path),
        "response_hash": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
    }
    (output_dir / f"{dataset}.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    if status != "failed":
        store.persist_source_daily_metrics(source, run_id, daily_metrics, status=status)
    return manifest
