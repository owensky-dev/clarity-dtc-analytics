from __future__ import annotations

import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path


_SNAPSHOT_DATE_RE = re.compile(r"(?:snapshot_id|run_id)=(\d{4}-\d{2}-\d{2})")


def cleanup_raw_snapshots(
    project_root: Path, *, retention_days: int, now: datetime | None = None
) -> list[Path]:
    """Remove only dated raw run folders older than the explicit local retention policy."""
    if retention_days < 1:
        raise ValueError("RAW_RETENTION_DAYS must be at least 1.")
    cutoff = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date() - timedelta(days=retention_days)
    raw_root = project_root / "data" / "raw"
    deleted: list[Path] = []
    if not raw_root.exists():
        return deleted
    for source_dir in raw_root.iterdir():
        if not source_dir.is_dir():
            continue
        candidates = source_dir.rglob("*") if source_dir.name == "clarity" else source_dir.glob("run_id=*")
        for candidate in candidates:
            if not candidate.is_dir():
                continue
            match = _SNAPSHOT_DATE_RE.search(candidate.name)
            if not match:
                continue
            try:
                candidate_date = datetime.fromisoformat(match.group(1)).date()
            except ValueError:
                continue
            if candidate_date < cutoff:
                shutil.rmtree(candidate)
                deleted.append(candidate)
    return deleted
