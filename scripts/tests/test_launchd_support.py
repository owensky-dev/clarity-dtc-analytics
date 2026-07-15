from __future__ import annotations

import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

try:
    import launchd_support
except ModuleNotFoundError:
    launchd_support = None


class LaunchdSupportTests(unittest.TestCase):
    def test_launchd_bundle_uses_absolute_paths_and_default_schedule(self) -> None:
        self.assertIsNotNone(launchd_support)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = launchd_support.build_launchd_bundle(
                project_root=Path("/Users/test/projects/store"),
                store_slug="demo-store",
                runtime_python=Path("/Users/test/.venv/bin/python"),
                automation_root=root,
            )
            self.assertTrue(bundle.wrapper_path.is_file())
            payload = plistlib.loads(bundle.plist_path.read_bytes())
            self.assertEqual(payload["StartCalendarInterval"], {"Hour": 8, "Minute": 30})
            self.assertEqual(payload["ProgramArguments"][0], "/bin/zsh")
            wrapper = bundle.wrapper_path.read_text(encoding="utf-8")
            self.assertIn("/Users/test/projects/store", wrapper)
            self.assertNotIn("\nexec ", wrapper)
            self.assertIn("trap cleanup EXIT", wrapper)
            self.assertIn('rmdir -- "$lock_path"', wrapper)
            self.assertIn("PATH", payload["EnvironmentVariables"])

    def test_launchd_bundle_preserves_virtualenv_interpreter_symlink(self) -> None:
        self.assertIsNotNone(launchd_support)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_python = root / "python-base"
            base_python.write_text("", encoding="utf-8")
            venv_python = root / ".venv" / "bin" / "python"
            venv_python.parent.mkdir(parents=True)
            venv_python.symlink_to(base_python)
            bundle = launchd_support.build_launchd_bundle(
                project_root=root / "project",
                store_slug="demo-store",
                runtime_python=venv_python.absolute(),
                automation_root=root / "automation",
            )
            self.assertIn(str(venv_python), bundle.wrapper_path.read_text(encoding="utf-8"))

    @unittest.skipUnless(Path("/bin/zsh").is_file(), "requires macOS /bin/zsh")
    def test_wrapper_removes_lock_after_successful_run(self) -> None:
        self.assertIsNotNone(launchd_support)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            runner = project / "scripts" / "run_daily_ingestion.py"
            runner.parent.mkdir(parents=True)
            runner.write_text("exit 0\n", encoding="utf-8")
            bundle = launchd_support.build_launchd_bundle(
                project_root=project,
                store_slug="demo-store",
                runtime_python=Path("/bin/sh"),
                automation_root=root / "automation",
            )
            subprocess.run(["/bin/zsh", str(bundle.wrapper_path)], check=True)
            self.assertFalse((bundle.wrapper_path.parent / "run.lock").exists())


if __name__ == "__main__":
    unittest.main()
