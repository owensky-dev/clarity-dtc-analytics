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

## Clarity

Each successful query stores `response.json` and `manifest.json`. A manifest includes requested dimensions, UTC snapshot bounds, HTTP status, bytes, response hash, metric row counts, maximum metric rows, schema mismatch, and truncation risk.

Store every Clarity metric information row with `snapshot_id`, `query_pack`, `metric_name`, `row_index`, nullable raw dimensions, canonical URL, numeric fields, and raw JSON. Never join metric arrays by row position. Preserve `null` and empty dimensions as received.

Use only the `URL × Device × Channel` slice for aggregate friction summaries to avoid summing overlapping query packs. A response where any metric reaches 1,000 rows is `partial`; preserve its raw response and manifest, but do not write its facts into DuckDB or use it as CRO evidence.

The snapshot anchor is a configured fixed UTC clock time. Its manifest contains an exact 24-hour start/end range and is the canonical window definition; its directory key must never be interpreted as a store-calendar day. A rerun for the same anchor reuses the existing ledger entry rather than creating an overlapping slice.

## Four-source facts

- Shopify daily facts: `date`, `orders`, `revenue`; a date with zero orders is a valid complete row.
- GA4 channel facts: `date`, sessions, engaged sessions, conversions, ecommerce purchases, and GA4 revenue.
- GA4 funnel-event raw facts: `date`, sanitized `landingPagePlusQueryString`, `eventName`, and `eventCount`, limited to `add_to_cart` and `begin_checkout`. Remove the query string before local persistence so checkout tokens and tracking parameters are not stored. Daily warehouse facts add `add_to_cart` and `begin_checkout`; channel rows remain the source of date coverage so an event-only row cannot create false GA4 completeness.
- Google Ads: clicks, spend, conversions, conversion value. Convert micros to normal currency before staging.
- GSC: clicks and impressions; calculate CTR only after aggregation. Use a `date`-only Search Console query for daily report facts. High-cardinality `date × page × query × country × device` rows are diagnostic raw data and must not be treated as complete totals.

The weekly finance report requires every source to cover both comparison weeks. Clarity coverage does not block the four-source finance report, but an unavailable or partial Clarity slice must disable associated CRO evidence.

Weekly funnel rates use the aligned report window: add-to-cart rate is `add_to_cart / sessions`, cart-to-checkout rate is `begin_checkout / add_to_cart`, and store conversion rate is Shopify orders divided by GA4 sessions.
