# Data Contract

## Local layout

```text
data/raw/<source>/run_id=<UTC timestamp>/
data/staged/<source>/run_id=<UTC timestamp>/
data/warehouse/analytics.duckdb
data/state/clarity_runs.jsonl
reports/
outputs/
```

Raw source responses are immutable run evidence. Staged Parquet is a queryable export. DuckDB contains normalized long rows and report facts.

Each four-source manifest records expected and actual date coverage, raw and daily schemas, plus source-specific contract metadata. Empty or incomplete requested-date daily rollups are `failed` and must not create warehouse coverage. Shopify order-level raw rows must satisfy the required schema and reconcile exactly to the six daily business/channel metrics before coverage is written. A complete all-zero source window remains `valid_zero`; in particular, zero Shopify qualified orders are valid because the complete date scaffold distinguishes zero sales from a missing fetch.

## Clarity

Each successful query stores `response.json` and `manifest.json`. A manifest includes requested dimensions, UTC snapshot bounds, HTTP status, bytes, response hash, metric row counts, maximum metric rows, schema mismatch, and truncation risk.

Store every Clarity metric information row with `snapshot_id`, `query_pack`, `metric_name`, `row_index`, nullable raw dimensions, canonical URL, numeric fields, and raw JSON. Never join metric arrays by row position. Preserve `null` and empty dimensions as received.

For `url_country_device`, if the Clarity Export API returns `URL` and `Device` but omits `Country/Region`, treat the slice as degraded complete: preserve rows with `country_region = null`, add `missing_dimensions` and `degraded_dimensions` to the manifest, and do not count it as a blocking schema mismatch. Missing `URL` or `Device` remains a schema mismatch.

Use only the `URL × Device × Channel` slice for aggregate friction summaries to avoid summing overlapping query packs. A response where any metric reaches 1,000 rows is `partial`; preserve its raw response and manifest, but do not write its facts into DuckDB or use it as CRO evidence.

The snapshot anchor is a configured fixed UTC clock time. Its manifest contains an exact 24-hour start/end range and is the canonical window definition; its directory key must never be interpreted as a store-calendar day. A rerun for the same anchor reuses the existing ledger entry rather than creating an overlapping slice.

## Four-source facts

- Shopify raw order facts include `financial_status`, `test`, `cancelled_at`, and `source_name`. Convert `created_at` to `REPORT_TIMEZONE`, then strictly keep only requested local dates. Shopify daily business facts count only paid, non-test, non-cancelled orders and persist `orders`, `revenue`, `online_store_orders`, `online_store_revenue`, `offsite_orders`, and `offsite_revenue`; a successfully fetched date with zero qualified orders is a valid complete row.
- GA4 channel facts: `date`, sessions, engaged sessions, conversions, ecommerce purchases, and GA4 revenue.
- GA4 funnel-event raw facts: `date`, sanitized `landingPagePlusQueryString`, `eventName`, and `eventCount`, limited to `add_to_cart` and `begin_checkout`. Remove the query string before local persistence so checkout tokens and tracking parameters are not stored. Daily warehouse facts add `add_to_cart` and `begin_checkout`; channel rows remain the source of date coverage so an event-only row cannot create false GA4 completeness.
- Google Ads: clicks, spend, conversions, conversion value. Convert micros to normal currency before staging.
- GSC: clicks and impressions; calculate CTR only after aggregation. Use an explicit `type=web`, `aggregationType=byProperty`, `date`-only Search Console query for daily report facts. High-cardinality `date × page × query × country × device` rows are diagnostic raw data and must not be treated as complete totals.

The weekly finance report requires every source to cover both comparison weeks. Automatic report generation also requires GA4, GSC, Google Ads, and Shopify to complete in the current ingestion run; a current failure cannot fall back to old warehouse coverage. Clarity coverage does not block the four-source finance report, but an unavailable or partial Clarity slice must disable associated CRO evidence.

Weekly funnel rates use the aligned report window: add-to-cart rate is `add_to_cart / sessions`, cart-to-checkout rate is `begin_checkout / add_to_cart`, and store conversion rate is Shopify orders divided by GA4 sessions.

Weekly purchase-integrity fields use the same aligned window:

- `purchase_count_gap = Shopify Online Store orders - GA4 ecommerce purchases`
- `purchase_revenue_gap = Shopify Online Store revenue - GA4 revenue`
- `purchase_tracking_rate = GA4 ecommerce purchases / Shopify Online Store orders`

A positive count gap is a high-risk signal, not transaction-level evidence. Exact reconciliation requires BigQuery `transaction_id` matched to Shopify Online Store paid, non-test, non-cancelled orders; no customer data belongs in the report output.
