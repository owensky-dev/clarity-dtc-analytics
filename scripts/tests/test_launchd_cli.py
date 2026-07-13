from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"


class LaunchdCliTests(unittest.TestCase):
    def test_launchd_cli_documents_install_and_check_modes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(TEMPLATE_SCRIPTS / "manage_launchd.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--install", result.stdout)
        self.assertIn("--check", result.stdout)


if __name__ == "__main__":
    unittest.main()
