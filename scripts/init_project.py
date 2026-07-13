from __future__ import annotations

import argparse
import shutil
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parent / "template"


def _copy_file(source: Path, destination: Path, overwrite: bool) -> None:
    if destination.exists() and not overwrite:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def install_project(target: Path, overwrite: bool = False) -> None:
    """Create an isolated store project without copying local secrets."""
    target = target.expanduser().resolve()
    for relative in (
        "data/raw",
        "data/staged",
        "data/warehouse",
        "data/state",
        "reports",
        "outputs",
        "logs",
        "scripts",
    ):
        (target / relative).mkdir(parents=True, exist_ok=True)
    for source in TEMPLATE_DIR.glob("*.py"):
        _copy_file(source, target / "scripts" / source.name, overwrite)
    for filename in (".env.example", ".gitignore", "requirements.txt"):
        _copy_file(TEMPLATE_DIR / filename, target / filename, overwrite)


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize a local Clarity DTC analytics project.")
    parser.add_argument("--target", default=".", help="Project directory to create or update.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite copied template files.")
    args = parser.parse_args()
    install_project(Path(args.target), overwrite=args.overwrite)
    print(f"Initialized Clarity DTC analytics project: {Path(args.target).expanduser().resolve()}")


if __name__ == "__main__":
    main()
