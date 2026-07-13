from __future__ import annotations

from urllib.parse import urlparse, urlunparse


DEVICE_MAP = {
    "pc": "desktop",
    "desktop": "desktop",
    "mobile": "mobile",
    "chromemobile": "mobile",
    "mobile safari": "mobile",
    "tablet": "tablet",
}


def canonical_url(value: str | None) -> str:
    """Return a path-level URL key without fragments or query parameters."""
    if not value:
        return ""
    parsed = urlparse(str(value).strip())
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, host, path, "", "", ""))


def normalize_device(value: str | None) -> str:
    """Map source-specific device labels to the warehouse taxonomy."""
    key = str(value or "").strip().lower()
    return DEVICE_MAP.get(key, "other")
