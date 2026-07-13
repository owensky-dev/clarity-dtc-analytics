from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from launchd_support import build_launchd_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Create, install, or inspect a local launchd daily analytics task.")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--store-slug", required=True)
    parser.add_argument("--runtime-python", default=sys.executable)
    parser.add_argument("--hour", type=int, default=8)
    parser.add_argument("--minute", type=int, default=30)
    parser.add_argument("--automation-root", default=str(Path.home() / ".codex" / "automations" / "clarity-dtc-analytics"))
    parser.add_argument("--install", action="store_true", help="Copy the generated plist into ~/Library/LaunchAgents and load it.")
    parser.add_argument("--check", action="store_true", help="Print launchctl state for the generated label.")
    args = parser.parse_args()
    bundle = build_launchd_bundle(
        project_root=Path(args.project_root).expanduser().resolve(),
        store_slug=args.store_slug,
        runtime_python=Path(args.runtime_python).expanduser().resolve(),
        automation_root=Path(args.automation_root).expanduser().resolve(),
        hour=args.hour,
        minute=args.minute,
    )
    if args.install:
        target = Path.home() / "Library" / "LaunchAgents" / f"{bundle.label}.plist"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundle.plist_path, target)
        uid = str(__import__("os").getuid())
        subprocess.run(["launchctl", "bootout", f"gui/{uid}", bundle.label], check=False, capture_output=True)
        subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(target)], check=True)
        print(f"Installed {bundle.label}: {target}")
    elif args.check:
        uid = str(__import__("os").getuid())
        result = subprocess.run(["launchctl", "print", f"gui/{uid}/{bundle.label}"], check=False, text=True)
        return result.returncode
    else:
        print(f"Generated wrapper: {bundle.wrapper_path}")
        print(f"Generated plist: {bundle.plist_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
