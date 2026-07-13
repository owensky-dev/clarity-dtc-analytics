from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"


class WeeklyCliTests(unittest.TestCase):
    def test_weekly_report_cli_exposes_project_root(self) -> None:
        result = subprocess.run(
            [sys.executable, str(TEMPLATE_SCRIPTS / "generate_weekly_report.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--project-root", result.stdout)


if __name__ == "__main__":
    unittest.main()
