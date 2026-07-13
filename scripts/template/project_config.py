from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigError(RuntimeError):
    pass


BASE_REQUIRED_KEYS = ("REPORT_TIMEZONE", "STORE_CURRENCY")
SOURCE_REQUIRED_KEYS = {
    "clarity": ("CLARITY_PROJECT_ID", "CLARITY_EXPORT_TOKEN"),
    "ga4": ("GOOGLE_APPLICATION_CREDENTIALS", "GA4_PROPERTY_ID"),
    "gsc": ("GOOGLE_APPLICATION_CREDENTIALS", "GSC_SITE_URL"),
    "google_ads": (
        "GOOGLE_ADS_CUSTOMER_ID",
        "GOOGLE_ADS_DEVELOPER_TOKEN",
        "GOOGLE_ADS_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET",
        "GOOGLE_ADS_REFRESH_TOKEN",
    ),
    "shopify": ("SHOPIFY_SHOP_DOMAIN", "SHOPIFY_ADMIN_ACCESS_TOKEN"),
}


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_project_settings(project_root: Path) -> dict[str, str]:
    """Load local config while requiring a deliberately chosen reporting timezone."""
    settings = _read_dotenv(project_root / ".env")
    for key, value in os.environ.items():
        if value:
            settings[key] = value
    missing = [key for key in BASE_REQUIRED_KEYS if not settings.get(key)]
    if missing:
        raise ConfigError(f"Missing required configuration: {', '.join(missing)}")
    try:
        ZoneInfo(settings["REPORT_TIMEZONE"])
    except ZoneInfoNotFoundError as error:
        raise ConfigError(f"Invalid REPORT_TIMEZONE: {settings['REPORT_TIMEZONE']}") from error
    try:
        retention_days = int(settings.get("RAW_RETENTION_DAYS", "400"))
        snapshot_hour = int(settings.get("CLARITY_SNAPSHOT_UTC_HOUR", "0"))
        snapshot_minute = int(settings.get("CLARITY_SNAPSHOT_UTC_MINUTE", "0"))
    except ValueError as error:
        raise ConfigError("RAW_RETENTION_DAYS and Clarity snapshot UTC time must be integers.") from error
    if retention_days < 1:
        raise ConfigError("RAW_RETENTION_DAYS must be at least 1.")
    if not (0 <= snapshot_hour <= 23 and 0 <= snapshot_minute <= 59):
        raise ConfigError("Clarity snapshot UTC hour/minute are outside the valid clock range.")
    return settings


def require_source(settings: dict[str, str], source: str) -> None:
    if source not in SOURCE_REQUIRED_KEYS:
        raise ConfigError(f"Unknown source: {source}")
    missing = [key for key in SOURCE_REQUIRED_KEYS[source] if not settings.get(key)]
    if missing:
        raise ConfigError(f"Missing {source} configuration: {', '.join(missing)}")
