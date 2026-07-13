from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"


class ValidateConfigCliTests(unittest.TestCase):
    def test_validator_reports_missing_source_credentials_without_echoing_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("REPORT_TIMEZONE=America/Los_Angeles\nSTORE_CURRENCY=USD\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(TEMPLATE_SCRIPTS / "validate_config.py"), "--project-root", str(root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("clarity", result.stdout)
            self.assertNotIn("CLARITY_EXPORT_TOKEN=", result.stdout)


if __name__ == "__main__":
    unittest.main()
