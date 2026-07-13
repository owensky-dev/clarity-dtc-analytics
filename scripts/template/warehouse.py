from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clarity_export import ParsedClarityPayload, build_behavior_facts


def _load_duckdb() -> Any:
    try:
        import duckdb
    except ModuleNotFoundError as error:
        raise RuntimeError("DuckDB is required. Run: python -m pip install -r requirements.txt") from error
    return duckdb


class AnalyticsWarehouse:
    """Small local DuckDB warehouse with immutable source-level snapshots."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.database_path = project_root / "data" / "warehouse" / "analytics.duckdb"
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connection(self) -> Any:
        return _load_duckdb().connect(str(self.database_path))

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS clarity_snapshots (
                    snapshot_id VARCHAR,
                    query_pack VARCHAR,
                    fetched_at_utc VARCHAR,
                    schema_mismatch BOOLEAN,
                    row_count BIGINT,
                    manifest_json VARCHAR
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS clarity_metric_rows (
                    snapshot_id VARCHAR,
                    query_pack VARCHAR,
                    metric_name VARCHAR,
                    row_index BIGINT,
                    raw_url VARCHAR,
                    canonical_url VARCHAR,
                    device VARCHAR,
                    channel VARCHAR,
                    dimensions_json VARCHAR,
                    numeric_json VARCHAR,
                    raw_information_json VARCHAR
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS clarity_behavior_facts (
                    snapshot_id VARCHAR,
                    query_pack VARCHAR,
                    raw_url VARCHAR,
                    canonical_url VARCHAR,
                    device VARCHAR,
                    channel VARCHAR,
                    source VARCHAR,
                    medium VARCHAR,
                    campaign VARCHAR,
                    country_region VARCHAR,
                    total_sessions DOUBLE,
                    dead_click_count DOUBLE,
                    rage_click_count DOUBLE,
                    error_click_count DOUBLE,
                    script_error_count DOUBLE,
                    quickback_click_count DOUBLE,
                    excessive_scroll_count DOUBLE,
                    average_scroll_depth DOUBLE,
                    active_time_seconds DOUBLE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS source_daily_metrics (
                    source VARCHAR,
                    date VARCHAR,
                    run_id VARCHAR,
                    status VARCHAR,
                    metrics_json VARCHAR
                )
                """
            )

    def persist_clarity_snapshot(
        self, manifest: dict[str, Any], parsed: ParsedClarityPayload
    ) -> None:
        snapshot_id = str(manifest["snapshot_id"])
        query_pack = str(manifest["query_pack"])
        if any(row["snapshot_id"] != snapshot_id or row["query_pack"] != query_pack for row in parsed.metric_rows):
            raise ValueError("Manifest and parsed Clarity rows must refer to the same snapshot and query pack.")
        with self._connection() as connection:
            for table in ("clarity_snapshots", "clarity_metric_rows", "clarity_behavior_facts"):
                connection.execute(
                    f"DELETE FROM {table} WHERE snapshot_id = ? AND query_pack = ?",
                    [snapshot_id, query_pack],
                )
            connection.execute(
                "INSERT INTO clarity_snapshots VALUES (?, ?, ?, ?, ?, ?)",
                [
                    snapshot_id,
                    query_pack,
                    manifest.get("fetched_at_utc"),
                    bool(manifest.get("schema_mismatch")),
                    int(manifest.get("row_count", 0)),
                    json.dumps(manifest, ensure_ascii=False, sort_keys=True),
                ],
            )
            if parsed.metric_rows:
                connection.executemany(
                    "INSERT INTO clarity_metric_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            row["snapshot_id"],
                            row["query_pack"],
                            row["metric_name"],
                            row["row_index"],
                            row["raw_url"],
                            row["canonical_url"],
                            row["device"],
                            row["channel"],
                            row["dimensions_json"],
                            json.dumps(row["numeric"], ensure_ascii=False, sort_keys=True),
                            row["raw_information_json"],
                        )
                        for row in parsed.metric_rows
                    ],
                )
            facts = build_behavior_facts(parsed.metric_rows)
            if facts:
                connection.executemany(
                    "INSERT INTO clarity_behavior_facts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            fact["snapshot_id"],
                            fact["query_pack"],
                            fact.get("raw_url"),
                            fact.get("canonical_url"),
                            fact.get("device"),
                            fact.get("channel"),
                            fact.get("source"),
                            fact.get("medium"),
                            fact.get("campaign"),
                            fact.get("country_region"),
                            fact.get("total_sessions"),
                            fact.get("dead_click_count"),
                            fact.get("rage_click_count"),
                            fact.get("error_click_count"),
                            fact.get("script_error_count"),
                            fact.get("quickback_click_count"),
                            fact.get("excessive_scroll_count"),
                            fact.get("average_scroll_depth"),
                            fact.get("active_time_seconds"),
                        )
                        for fact in facts
                    ],
                )
            self._write_metric_rows_parquet(connection, snapshot_id, query_pack)

    def _write_metric_rows_parquet(self, connection: Any, snapshot_id: str, query_pack: str) -> None:
        safe_snapshot_id = snapshot_id.replace(":", "-")
        output_dir = (
            self.project_root / "data" / "staged" / "clarity" / f"snapshot_id={safe_snapshot_id}"
            / f"query_pack={query_pack}"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "metric_rows.parquet"
        if output_path.exists():
            output_path.unlink()
        escaped_path = str(output_path).replace("'", "''")
        connection.execute(
            "COPY (SELECT * FROM clarity_metric_rows WHERE snapshot_id = ? AND query_pack = ?) "
            f"TO '{escaped_path}' (FORMAT PARQUET)",
            [snapshot_id, query_pack],
        )

    def count_rows(self, table: str) -> int:
        if table not in {"clarity_snapshots", "clarity_metric_rows", "clarity_behavior_facts", "source_daily_metrics"}:
            raise ValueError(f"Unsupported warehouse table: {table}")
        with self._connection() as connection:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def persist_source_daily_metrics(
        self, source: str, run_id: str, rows: list[dict[str, Any]], status: str = "complete"
    ) -> None:
        if status not in {"complete", "valid_zero"}:
            raise ValueError(f"Unsupported source metric status: {status}")
        normalized: list[tuple[str, str, str, str, str]] = []
        for row in rows:
            date_value = str(row.get("date", ""))
            if not date_value:
                raise ValueError("Every source daily metric requires a date.")
            metrics = {key: value for key, value in row.items() if key != "date"}
            normalized.append(
                (source, date_value, run_id, status, json.dumps(metrics, ensure_ascii=False, sort_keys=True))
            )
        with self._connection() as connection:
            for _, date_value, _, _, _ in normalized:
                connection.execute(
                    "DELETE FROM source_daily_metrics WHERE source = ? AND date = ?",
                    [source, date_value],
                )
            if normalized:
                connection.executemany("INSERT INTO source_daily_metrics VALUES (?, ?, ?, ?, ?)", normalized)
            self._write_source_metrics_parquet(connection, source, run_id)

    def _write_source_metrics_parquet(self, connection: Any, source: str, run_id: str) -> None:
        output_dir = self.project_root / "data" / "staged" / source / f"run_id={run_id.replace(':', '-')}"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "daily_metrics.parquet"
        if output_path.exists():
            output_path.unlink()
        escaped_path = str(output_path).replace("'", "''")
        connection.execute(
            "COPY (SELECT * FROM source_daily_metrics WHERE source = ? AND run_id = ?) "
            f"TO '{escaped_path}' (FORMAT PARQUET)",
            [source, run_id],
        )

    def source_complete_dates(self, source: str) -> set[str]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT DISTINCT date FROM source_daily_metrics WHERE source = ? AND status IN ('complete', 'valid_zero')",
                [source],
            ).fetchall()
        return {str(row[0]) for row in rows}

    def source_daily_metrics(self, source: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT date, metrics_json
                FROM source_daily_metrics
                WHERE source = ? AND date BETWEEN ? AND ? AND status IN ('complete', 'valid_zero')
                ORDER BY date
                """,
                [source, start_date, end_date],
            ).fetchall()
        return [{"date": str(row[0]), **json.loads(row[1])} for row in rows]

    def clarity_friction_summary(self, start_date: str, end_date: str) -> dict[str, float]:
        """Summarize a non-overlapping Clarity slice for evidence, never for revenue attribution."""
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT
                  COALESCE(SUM(total_sessions), 0),
                  COALESCE(SUM(dead_click_count), 0),
                  COALESCE(SUM(rage_click_count), 0),
                  COALESCE(SUM(error_click_count), 0),
                  COALESCE(SUM(script_error_count), 0),
                  COALESCE(SUM(quickback_click_count), 0),
                  COALESCE(SUM(excessive_scroll_count), 0)
                FROM clarity_behavior_facts
                WHERE query_pack = 'url_device_channel'
                  AND SUBSTRING(snapshot_id, 1, 10) BETWEEN ? AND ?
                """,
                [start_date, end_date],
            ).fetchone()
        keys = (
            "sessions",
            "dead_clicks",
            "rage_clicks",
            "error_clicks",
            "script_errors",
            "quickbacks",
            "excessive_scrolls",
        )
        return {key: float(value or 0) for key, value in zip(keys, row)}

    def clarity_page_friction(self, start_date: str, end_date: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return high-friction page/device/channel evidence from one non-overlapping query pack."""
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT canonical_url, device, channel,
                  COALESCE(SUM(total_sessions), 0) AS sessions,
                  COALESCE(SUM(dead_click_count), 0) AS dead_clicks,
                  COALESCE(SUM(rage_click_count), 0) AS rage_clicks,
                  COALESCE(SUM(error_click_count), 0) AS error_clicks,
                  COALESCE(SUM(script_error_count), 0) AS script_errors,
                  COALESCE(SUM(quickback_click_count), 0) AS quickbacks
                FROM clarity_behavior_facts
                WHERE query_pack = 'url_device_channel'
                  AND canonical_url <> ''
                  AND SUBSTRING(snapshot_id, 1, 10) BETWEEN ? AND ?
                GROUP BY canonical_url, device, channel
                ORDER BY (COALESCE(SUM(error_click_count), 0) * 2 + COALESCE(SUM(script_error_count), 0) * 2
                          + COALESCE(SUM(dead_click_count), 0) * 1.5 + COALESCE(SUM(rage_click_count), 0)
                          + COALESCE(SUM(quickback_click_count), 0) * 1.2) DESC, sessions DESC
                LIMIT ?
                """,
                [start_date, end_date, limit],
            ).fetchall()
        records = []
        for row in rows:
            sessions = float(row[3] or 0)
            record = dict(zip(("canonical_url", "device", "channel", "sessions", "dead_clicks", "rage_clicks", "error_clicks", "script_errors", "quickbacks"), row))
            record.update({
                "dead_click_rate": float(record["dead_clicks"] or 0) / sessions if sessions else None,
                "rage_click_rate": float(record["rage_clicks"] or 0) / sessions if sessions else None,
                "error_click_rate": float(record["error_clicks"] or 0) / sessions if sessions else None,
                "script_error_rate": float(record["script_errors"] or 0) / sessions if sessions else None,
            })
            records.append(record)
        return records
