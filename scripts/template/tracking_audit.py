from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


ALLOWED_EVENTS = {
    "view_product",
    "select_variant",
    "variant_error",
    "add_to_cart",
    "open_cart",
    "remove_from_cart",
    "apply_coupon",
    "coupon_error",
    "begin_checkout",
    "checkout_error",
    "purchase",
    "open_quote_form",
    "submit_quote",
    "upload_drawing",
    "download_spec",
    "open_installation_guide",
    "shipping_estimate",
    "financing_click",
    "contact_support",
}
ALLOWED_TAGS = {
    "page_type",
    "product_category",
    "product_id",
    "price_band",
    "stock_status",
    "cart_value_band",
    "customer_type",
    "traffic_intent",
    "experiment",
    "landing_type",
    "lead_type",
    "template_version",
}
PII_KEY_RE = re.compile(r"(email|phone|name|address|customer|order|note|comment)", re.IGNORECASE)
EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")


@dataclass(frozen=True)
class TrackingAuditResult:
    checkout_capture_status: str
    safe_to_deploy: bool
    issues: list[str]
    warnings: list[str]
    implementation_snippets: str


def _contains_pii(key: str, value: Any) -> bool:
    text = str(value or "")
    return bool(EMAIL_RE.search(text) or PHONE_RE.search(text))


def audit_tracking_plan(
    *, setup: dict[str, Any], events: list[str], tags: dict[str, Any]
) -> TrackingAuditResult:
    """Validate a non-PII Clarity tracking plan without changing the storefront."""
    issues: list[str] = []
    warnings: list[str] = []
    if not setup.get("clarity_app_installed"):
        warnings.append("Microsoft Clarity Shopify App is not confirmed.")
    if not setup.get("clarity_js_enabled"):
        warnings.append("Clarity JavaScript is not confirmed as enabled.")
    if not setup.get("consent_mode_configured"):
        warnings.append("Consent mode is not confirmed; EEA/UK/Swiss coverage may be incomplete.")

    full_checkout = all(
        (
            setup.get("shopify_plus"),
            setup.get("clarity_app_installed"),
            setup.get("clarity_js_enabled"),
            setup.get("shopify_pixel_verified"),
        )
    )
    checkout_capture_status = "full" if full_checkout else "storefront_only"
    if checkout_capture_status == "storefront_only":
        warnings.append("Use GA4 and Shopify for checkout diagnosis; Clarity checkout capture is not verified.")

    event_lines: list[str] = []
    for event in events:
        if event not in ALLOWED_EVENTS:
            issues.append(f"Event is not in the allowlist: {event}")
            continue
        event_lines.append(f'window.clarity("event", "{event}");')
    tag_lines: list[str] = []
    for key, value in tags.items():
        if key not in ALLOWED_TAGS:
            issues.append(f"Custom tag is not in the allowlist: {key}")
            continue
        if PII_KEY_RE.search(key) and key != "customer_type":
            issues.append(f"PII-like custom tag is prohibited: {key}")
            continue
        if _contains_pii(key, value):
            issues.append(f"PII-like custom tag is prohibited: {key}")
            continue
        tag_lines.append(f'window.clarity("set", "{key}", {value!r});')
    snippets = "\n".join(event_lines + tag_lines)
    return TrackingAuditResult(
        checkout_capture_status=checkout_capture_status,
        safe_to_deploy=not issues,
        issues=issues,
        warnings=warnings,
        implementation_snippets=snippets,
    )
