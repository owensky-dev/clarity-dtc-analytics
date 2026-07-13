from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"


class CliTests(unittest.TestCase):
    def test_daily_ingestion_cli_exposes_help(self) -> None:
        result = subprocess.run(
            [sys.executable, str(TEMPLATE_SCRIPTS / "run_daily_ingestion.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("daily", result.stdout.lower())
        self.assertIn("--project-root", result.stdout)


if __name__ == "__main__":
    unittest.main()
