from __future__ import annotations

import sys
import unittest
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

try:
    import tracking_audit
except ModuleNotFoundError:
    tracking_audit = None


class TrackingAuditTests(unittest.TestCase):
    def test_non_plus_store_is_storefront_only_and_pii_tags_are_rejected(self) -> None:
        self.assertIsNotNone(
            tracking_audit,
            "tracking_audit must provide the safe Clarity implementation audit",
        )
        result = tracking_audit.audit_tracking_plan(
            setup={
                "shopify_plus": False,
                "clarity_app_installed": True,
                "clarity_js_enabled": True,
                "shopify_pixel_verified": False,
                "consent_mode_configured": True,
            },
            events=["view_product", "add_to_cart", "checkout_error"],
            tags={"page_type": "product", "customer_email": "buyer@example.com"},
        )
        self.assertEqual(result.checkout_capture_status, "storefront_only")
        self.assertFalse(result.safe_to_deploy)
        self.assertTrue(any("customer_email" in issue for issue in result.issues))
        self.assertIn('window.clarity("event", "add_to_cart")', result.implementation_snippets)

    def test_allowlisted_anonymous_customer_type_tag_is_allowed(self) -> None:
        self.assertIsNotNone(tracking_audit)
        result = tracking_audit.audit_tracking_plan(
            setup={}, events=[], tags={"customer_type": "guest"}
        )
        self.assertTrue(result.safe_to_deploy)
        self.assertIn('window.clarity("set", "customer_type", \'guest\');', result.implementation_snippets)


if __name__ == "__main__":
    unittest.main()
