# Reporting Policy

## Source roles

Use Shopify for orders and revenue. Use GA4 for sessions and funnel events. Use Google Ads for spend and platform-attributed conversions. Use GSC for search demand. Use Clarity for aggregate interaction friction and human review conditions.

Do not merge platform channel fields as if they are session-level attribution. Retain raw source/channel labels and clearly state mappings.

## Daily report

Write a local data-health and severe-anomaly report. Require a minimum sample of 50 Clarity sessions and a configurable severe rate threshold. Each item must include: observed fact, cautious inference, validation action, and evidence confidence.

## Weekly report

Write HTML, Markdown, JSON, and `analysis_context` outputs. Include management summary, core funnel, source coverage, Clarity friction, page/device/channel evidence, and prioritized experiments. At the top of HTML and Markdown outputs, show `周报周期` for the current 7 days and `对比周期` for the prior 7 days. Show rates as percentages. Show Google Ads CPA as `n/a` when conversions are zero.

## Optional AI narrative

Pass only structured, non-PII context. Require the model to separate observed facts, inferences, and validation questions. A model failure must leave the deterministic report intact.
