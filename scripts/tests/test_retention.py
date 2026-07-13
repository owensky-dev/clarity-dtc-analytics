from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

try:
    import retention
except ModuleNotFoundError:
    retention = None


class RetentionTests(unittest.TestCase):
    def test_cleanup_removes_only_expired_dated_raw_runs(self) -> None:
        self.assertIsNotNone(retention)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_run = root / "data" / "raw" / "ga4" / "run_id=2025-06-01T00-00-00Z"
            old_clarity = root / "data" / "raw" / "clarity" / "snapshot_id=2025-06-01T00-00-00Z"
            old_clarity_failure = root / "data" / "raw" / "clarity" / "run_id=2025-06-01T00-00-00Z"
            current_run = root / "data" / "raw" / "shopify" / "run_id=2026-07-12T00-00-00Z"
            for path in (old_run, old_clarity, old_clarity_failure, current_run):
                path.mkdir(parents=True)
            deleted = retention.cleanup_raw_snapshots(
                root, retention_days=400, now=datetime(2026, 7, 13, tzinfo=timezone.utc)
            )
            self.assertEqual(set(deleted), {old_run, old_clarity, old_clarity_failure})
            self.assertFalse(old_run.exists())
            self.assertFalse(old_clarity.exists())
            self.assertFalse(old_clarity_failure.exists())
            self.assertTrue(current_run.exists())
