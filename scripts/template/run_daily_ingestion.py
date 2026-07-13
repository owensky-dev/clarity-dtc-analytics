from __future__ import annotations

import argparse
import json
from pathlib import Path

from daily_runner import DailyIngestionRunner
from project_config import ConfigError, load_project_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run daily Clarity and four-source Shopify analytics ingestion.")
    parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Initialized store project directory.",
    )
    args = parser.parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    try:
        settings = load_project_settings(project_root)
        outcome = DailyIngestionRunner(project_root, settings).run()
    except ConfigError as error:
        raise SystemExit(f"Configuration error: {error}") from error
    print(
        json.dumps(
            {
                "clarity_successful_packs": outcome.clarity_successful_packs,
                "source_status": outcome.source_status,
                "weekly_report_path": str(outcome.weekly_report_path) if outcome.weekly_report_path else None,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
