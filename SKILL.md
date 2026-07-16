---
name: clarity-dtc-analytics
description: Build and operate a local, evidence-first Shopify analytics warehouse that saves daily Microsoft Clarity snapshots and integrates GA4, GSC, Google Ads, and Shopify. Use when Codex needs to initialize a store analytics project, validate data-source configuration, audit Clarity tracking, run daily ingestion, investigate CRO friction, or generate Chinese weekly conversion reports from these sources.
---

# Clarity DTC Analytics

Create a per-store local warehouse for daily Clarity behavior evidence and four-source ecommerce reporting. Keep source roles separate: Shopify is revenue/orders, GA4 is traffic/funnel, Google Ads is paid-media performance, GSC is search demand, and Clarity is behavior evidence only.

Fetch GA4 `add_to_cart` and `begin_checkout` through a separate event query with `date`, `landingPagePlusQueryString`, and `eventName` dimensions. Do not add `eventName` to the channel Sessions query because that would change its aggregation grain.

## Initialize a store project

1. Run `python <skill-root>/scripts/init_project.py --target <store-project-path>`.
2. Create a virtual environment in the store project and install `requirements.txt`.
3. Copy `.env.example` to `.env`; never commit or expose `.env` values.
4. Run `python scripts/validate_config.py --project-root <store-project-path>`.

Require `REPORT_TIMEZONE` and `STORE_CURRENCY`. Do not fall back to the Mac timezone. Read [configuration.md](references/configuration.md) before resolving access issues.

## Audit tracking before analysis

Create two local JSON files: setup state and the proposed events/tags. Run `python scripts/audit_tracking.py --setup-file <setup.json> --plan-file <tracking-plan.json> --out-dir reports`.

Use the generated JavaScript only as a reviewed implementation suggestion. Do not change Shopify themes, pixels, checkout, or consent settings automatically. Read [clarity-tracking.md](references/clarity-tracking.md) for the permitted event/tag taxonomy and privacy rules.

## Run daily ingestion

Run `python scripts/run_daily_ingestion.py --project-root <store-project-path>`.

The run must:

- Save four Clarity query packs: overall, `URL × Device × Channel`, `Source × Medium × Campaign`, and `URL × Country/Region × Device`.
- Store raw responses and a per-query manifest before writing normalized data.
- Enforce Clarity's per-project quota with the local ledger; allow at most one retry only for failed 5xx/network responses.
- Keep Clarity windows as UTC rolling 24-hour snapshots. Do not relabel them as exact store-calendar days.
- Anchor each Clarity window to `CLARITY_SNAPSHOT_UTC_HOUR/MINUTE` (default `00:00`) so a rerun is idempotent; use manifest bounds as the actual evidence window.
- Continue available source collection when another source fails, but record the failed source explicitly.

Read [data-contract.md](references/data-contract.md) before changing schemas or query packs.

## Generate and interpret reports

Run `python scripts/generate_weekly_report.py --project-root <store-project-path>` only after all four core sources have history.

The weekly report must use the latest consecutive 14 dates covered by GA4, Shopify, Google Ads, and GSC: current 7 days versus prior 7 days. If no aligned window exists, report source/date gaps instead of generating a partial financial week.

At the top of both HTML and Markdown outputs, show `周报周期` for the current 7-day window and `对比周期` for the prior 7-day window. The period labels must come from the aligned report window.

The core funnel must compare current versus previous GA4 Sessions, `add_to_cart`, `begin_checkout`, and Shopify orders. Show add-to-cart rate, cart-to-checkout rate, and store conversion rate as percentages.

Treat Clarity as a separate evidence layer. Include observed facts, cautious inferences, reproducible Clarity filters, and validation actions; never claim causal behavior from aggregate metrics or recordings. Read [reporting-policy.md](references/reporting-policy.md) for metric and narrative rules.

When `LLM_MODE=openai` is configured, use `analysis_context_*.json` and the optional narrative helper. Keep deterministic JSON/Markdown/HTML reports valid if the model call fails.

## Schedule locally

Generate a launchd bundle with `python scripts/manage_launchd.py --project-root <store-project-path> --store-slug <slug>`. Add `--install` only after reviewing the generated wrapper and plist. Use `--check` to inspect the loaded job.

Keep launchd wrappers and logs under `~/.codex/automations/clarity-dtc-analytics/`; use absolute paths and do not run scheduled jobs from a protected Documents working directory.

For an operating store, add a separate daily health-check automation after the scheduled ingestion. It must verify that today's Clarity snapshot exists and that all four core-source statuses are `complete`. On the first failed check, inspect the manifests and logs, repair safe local/runtime issues, and rerun ingestion. Check again at least four hours later; notify the operator only when the second attempt cannot restore complete collection. Never silently leave a failed collection without an explicit operator notification.

## Resources

- [configuration.md](references/configuration.md): configuration and credentials.
- [data-contract.md](references/data-contract.md): storage, facts, coverage, and limits.
- [clarity-tracking.md](references/clarity-tracking.md): tracking audit and privacy rules.
- [reporting-policy.md](references/reporting-policy.md): report, anomaly, and AI narrative policy.
