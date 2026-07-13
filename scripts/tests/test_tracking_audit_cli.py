from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"


class TrackingAuditCliTests(unittest.TestCase):
    def test_tracking_audit_cli_writes_audit_without_storefront_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            setup_path = root / "setup.json"
            plan_path = root / "plan.json"
            setup_path.write_text(json.dumps({"shopify_plus": False, "clarity_app_installed": True, "clarity_js_enabled": True, "shopify_pixel_verified": False, "consent_mode_configured": True}), encoding="utf-8")
            plan_path.write_text(json.dumps({"events": ["add_to_cart"], "tags": {"page_type": "product"}}), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(TEMPLATE_SCRIPTS / "audit_tracking.py"), "--setup-file", str(setup_path), "--plan-file", str(plan_path), "--out-dir", str(root / "reports")],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            audit = json.loads((root / "reports" / "clarity_tracking_audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["checkout_capture_status"], "storefront_only")
            self.assertTrue((root / "reports" / "clarity_tracking_implementation.js").is_file())


if __name__ == "__main__":
    unittest.main()
