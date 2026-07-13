from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_narrative import write_optional_narrative
from project_config import ConfigError, load_project_settings
from reporting import DataCoverageError, generate_weekly_report
from warehouse import AnalyticsWarehouse


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the aligned four-source weekly CRO report.")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--out-dir", help="Defaults to <project-root>/outputs.")
    args = parser.parse_args()
    root = Path(args.project_root).expanduser().resolve()
    try:
        result = generate_weekly_report(AnalyticsWarehouse(root), Path(args.out_dir).expanduser().resolve() if args.out_dir else root / "outputs")
    except DataCoverageError as error:
        raise SystemExit(f"Weekly report not generated: {error}") from error
    try:
        settings = load_project_settings(root)
        narrative_status = write_optional_narrative(
            result.payload,
            settings,
            result.json_path.with_name(result.json_path.stem + "_ai.md"),
        )
    except ConfigError:
        narrative_status = "configuration_unavailable"
    print(json.dumps({"json": str(result.json_path), "markdown": str(result.markdown_path), "html": str(result.html_path), "analysis_context": str(result.analysis_context_path), "ai_narrative": narrative_status}, ensure_ascii=False))


if __name__ == "__main__":
    main()
