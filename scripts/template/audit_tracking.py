from __future__ import annotations

import argparse
import json
from pathlib import Path

from tracking_audit import audit_tracking_plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a Clarity tracking plan without modifying the Shopify storefront.")
    parser.add_argument("--setup-file", required=True, help="JSON file describing Shopify/Clarity setup state.")
    parser.add_argument("--plan-file", required=True, help="JSON file containing events and custom tags.")
    parser.add_argument("--out-dir", default="reports", help="Directory for audit and implementation files.")
    args = parser.parse_args()
    setup = json.loads(Path(args.setup_file).read_text(encoding="utf-8"))
    plan = json.loads(Path(args.plan_file).read_text(encoding="utf-8"))
    result = audit_tracking_plan(
        setup=setup,
        events=list(plan.get("events", [])),
        tags=dict(plan.get("tags", {})),
    )
    output_dir = Path(args.out_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "checkout_capture_status": result.checkout_capture_status,
        "safe_to_deploy": result.safe_to_deploy,
        "issues": result.issues,
        "warnings": result.warnings,
        "storefront_mutated": False,
    }
    (output_dir / "clarity_tracking_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "clarity_tracking_implementation.js").write_text(
        result.implementation_snippets + "\n", encoding="utf-8"
    )
    markdown = ["# Clarity 埋点审计", "", f"- Checkout 覆盖：{result.checkout_capture_status}", f"- 可安全实施：{'是' if result.safe_to_deploy else '否'}"]
    markdown += [f"- 问题：{issue}" for issue in result.issues]
    markdown += [f"- 提醒：{warning}" for warning in result.warnings]
    (output_dir / "clarity_tracking_audit.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
