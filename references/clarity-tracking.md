# Clarity Tracking and Privacy

## Setup audit

Confirm the Microsoft Clarity Shopify App, Clarity JavaScript, consent mode, and Pixel setup. Mark checkout coverage `full` only when Shopify Plus, the official app, Clarity JavaScript, and Shopify Pixel verification are all present. Otherwise use `storefront_only` and diagnose checkout with GA4 and Shopify.

## Allowed events

Use only fixed behavioral names such as `view_product`, `select_variant`, `variant_error`, `add_to_cart`, `open_cart`, `apply_coupon`, `coupon_error`, `begin_checkout`, `checkout_error`, `purchase`, `open_quote_form`, and `submit_quote`.

## Allowed tags

Use grouped context only: `page_type`, `product_category`, `product_id`, `price_band`, `stock_status`, `cart_value_band`, `customer_type`, `traffic_intent`, `experiment`, `landing_type`, `lead_type`, and `template_version`.

Never pass emails, phones, names, addresses, form responses, notes, raw customer IDs, raw order IDs, or any value that identifies a person. Clarity Export API does not promise export access to custom events or tags; use them for Clarity UI filtering and recording review only.
