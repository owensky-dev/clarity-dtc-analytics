from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_config import ConfigError, SOURCE_REQUIRED_KEYS, load_project_settings, require_source


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local configuration for the Clarity DTC analytics project.")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    root = Path(args.project_root).expanduser().resolve()
    try:
        settings = load_project_settings(root)
    except ConfigError as error:
        print(json.dumps({"base": "invalid", "error": str(error)}, ensure_ascii=False))
        return 1
    sources: dict[str, str] = {}
    for source in SOURCE_REQUIRED_KEYS:
        try:
            require_source(settings, source)
            sources[source] = "configured"
        except ConfigError:
            sources[source] = "missing_configuration"
    print(json.dumps({"base": "configured", "sources": sources}, ensure_ascii=False))
    return 0 if all(value == "configured" for value in sources.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
