from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SKILL_SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_SCRIPTS))

try:
    import init_project
except ModuleNotFoundError:
    init_project = None


class ProjectBootstrapTests(unittest.TestCase):
    def test_initializer_creates_isolated_store_project_without_secrets(self) -> None:
        self.assertIsNotNone(
            init_project,
            "init_project must create a per-store project from the bundled template",
        )
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "demo-store"
            init_project.install_project(target)
            self.assertTrue((target / ".env.example").is_file())
            self.assertIn(".env", (target / ".gitignore").read_text(encoding="utf-8"))
            self.assertFalse((target / ".env").exists())
            self.assertTrue((target / "data" / "raw").is_dir())
            self.assertTrue((target / "data" / "staged").is_dir())
            self.assertTrue((target / "data" / "warehouse").is_dir())
            self.assertTrue((target / "data" / "state").is_dir())
            self.assertTrue((target / "scripts" / "run_daily_ingestion.py").is_file())


if __name__ == "__main__":
    unittest.main()
