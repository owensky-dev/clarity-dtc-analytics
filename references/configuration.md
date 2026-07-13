# Configuration

Use `.env` only in an initialized store project. Keep values local.

## Required base settings

- `REPORT_TIMEZONE`: IANA store reporting zone, for example `America/Los_Angeles`.
- `STORE_CURRENCY`: reporting currency, for example `USD`.
- `SITE_BASE_URL`: storefront URL for URL normalization.

## Source credentials

- Clarity: `CLARITY_PROJECT_ID`, `CLARITY_EXPORT_TOKEN`.
- GA4: `GOOGLE_APPLICATION_CREDENTIALS`, `GA4_PROPERTY_ID`.
- GSC: `GOOGLE_APPLICATION_CREDENTIALS`, `GSC_SITE_URL`.
- Google Ads: `GOOGLE_ADS_CUSTOMER_ID`, developer token, OAuth client ID/secret, refresh token, and optional login customer ID.
- Shopify: `SHOPIFY_SHOP_DOMAIN`, `SHOPIFY_ADMIN_ACCESS_TOKEN`, `SHOPIFY_API_VERSION`.

`validate_config.py` reports configured or missing fields without echoing any credential values. Google Ads may require an MCC developer token; preserve a failed source manifest rather than substituting invented performance values.

## Optional settings

- `RAW_RETENTION_DAYS`: default `400`.
- `CLARITY_SNAPSHOT_UTC_HOUR` and `CLARITY_SNAPSHOT_UTC_MINUTE`: fixed UTC end time for the 24-hour Clarity snapshot; defaults to `00:00`. The manifest's UTC bounds, not a date label, define the evidence window.
- `LLM_MODE`: `off` or `openai`.
- `OPENAI_API_KEY`, `OPENAI_MODEL`: only for optional narrative generation.
- `LOG_LEVEL`: default `INFO`.

Raw runs older than `RAW_RETENTION_DAYS` are removed only from `data/raw/` after a daily run. DuckDB, staged data, reports, and unknown folders are not silently removed.
