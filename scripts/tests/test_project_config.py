from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

try:
    import project_config
except ModuleNotFoundError:
    project_config = None


class ProjectConfigTests(unittest.TestCase):
    def test_project_settings_require_explicit_reporting_timezone(self) -> None:
        self.assertIsNotNone(project_config)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("STORE_CURRENCY=USD\n", encoding="utf-8")
            with self.assertRaises(project_config.ConfigError) as context:
                project_config.load_project_settings(root)
            self.assertIn("REPORT_TIMEZONE", str(context.exception))

    def test_project_settings_reject_invalid_clarity_anchor_clock(self) -> None:
        self.assertIsNotNone(project_config)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "REPORT_TIMEZONE=America/Los_Angeles\nSTORE_CURRENCY=USD\nCLARITY_SNAPSHOT_UTC_HOUR=24\n",
                encoding="utf-8",
            )
            with self.assertRaises(project_config.ConfigError) as context:
                project_config.load_project_settings(root)
            self.assertIn("snapshot UTC", str(context.exception))


if __name__ == "__main__":
    unittest.main()
