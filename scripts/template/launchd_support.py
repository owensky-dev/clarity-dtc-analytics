from __future__ import annotations

import os
import plistlib
import shlex
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LaunchdBundle:
    label: str
    wrapper_path: Path
    plist_path: Path
    stdout_path: Path
    stderr_path: Path


def build_launchd_bundle(
    *,
    project_root: Path,
    store_slug: str,
    runtime_python: Path,
    automation_root: Path,
    hour: int = 8,
    minute: int = 30,
) -> LaunchdBundle:
    """Create a user-level launchd bundle without loading or scheduling it."""
    if not store_slug.replace("-", "").replace("_", "").isalnum():
        raise ValueError("store_slug may only contain letters, numbers, hyphens, and underscores.")
    label = f"com.openai.clarity-dtc-analytics.{store_slug}"
    run_dir = automation_root / store_slug
    run_dir.mkdir(parents=True, exist_ok=True)
    wrapper_path = run_dir / "run_daily.sh"
    stdout_path = run_dir / "launchd.stdout.log"
    stderr_path = run_dir / "launchd.stderr.log"
    lock_path = run_dir / "run.lock"
    runner = project_root / "scripts" / "run_daily_ingestion.py"
    wrapper_path.write_text(
        "\n".join(
            [
                "#!/bin/zsh",
                "set -eu",
                f"mkdir -p {shlex.quote(str(run_dir))}",
                f"lock_path={shlex.quote(str(lock_path))}",
                'if ! mkdir "$lock_path" 2>/dev/null; then exit 0; fi',
                'cleanup() { rmdir -- "$lock_path"; }',
                "trap cleanup EXIT",
                f"{shlex.quote(str(runtime_python))} {shlex.quote(str(runner))} --project-root {shlex.quote(str(project_root))}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    wrapper_path.chmod(0o700)
    plist_path = run_dir / f"{label}.plist"
    plist_payload = {
        "Label": label,
        "ProgramArguments": ["/bin/zsh", "-lc", str(wrapper_path)],
        "WorkingDirectory": str(run_dir),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "RunAtLoad": False,
        "StandardOutPath": str(stdout_path),
        "StandardErrorPath": str(stderr_path),
        "EnvironmentVariables": {
            "HOME": os.environ.get("HOME", str(Path.home())),
            "USER": os.environ.get("USER", ""),
            "LOGNAME": os.environ.get("LOGNAME", ""),
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        },
    }
    plist_path.write_bytes(plistlib.dumps(plist_payload, sort_keys=True))
    return LaunchdBundle(label, wrapper_path, plist_path, stdout_path, stderr_path)
