-- Raw landing schema for the synthetic e-commerce dataset.
--
-- These are the tables the data generator writes and the tables dbt reads. They
-- are shaped the way real ingestion shapes data, which is to say badly:
--
--   * Dates and timestamps are text, in several formats, because that is what
--     arrives from a CSV export or a webhook payload. Typing them here would
--     hide the exact work dbt exists to do.
--   * Statuses are free text with inconsistent casing.
--   * Money arrives both as a number and as a string with a currency symbol.
--   * There are duplicates, nulls, and rows that reference nothing.
--
-- Cleaning all of that is the demo's story. Do not tidy these tables.

CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.customers (
    customer_id   text,
    email         text,
    full_name     text,
    country       text,
    signup_at     text,
    plan          text,
    mrr           text,
    is_trial      text,
    referred_by   text,
    last_seen_at  text
);

CREATE TABLE IF NOT EXISTS raw.products (
    sku          text,
    name         text,
    category     text,
    price        text,
    cost         text,
    launched_at  text
);

CREATE TABLE IF NOT EXISTS raw.subscriptions (
    subscription_id  text,
    customer_id      text,
    plan             text,
    status           text,
    seats            text,
    mrr              text,
    started_at       text,
    ended_at         text
);

CREATE TABLE IF NOT EXISTS raw.orders (
    order_id     text,
    customer_id  text,
    placed_at    text,
    status       text,
    currency     text,
    total        text,
    channel      text,
    coupon_code  text
);

CREATE TABLE IF NOT EXISTS raw.order_items (
    order_id     text,
    sku          text,
    quantity     text,
    unit_price   text,
    discount     text
);

CREATE TABLE IF NOT EXISTS raw.payments (
    payment_id      text,
    order_id        text,
    method          text,
    status          text,
    amount          text,
    captured_at     text,
    failure_reason  text
);

CREATE TABLE IF NOT EXISTS raw.refunds (
    refund_id    text,
    payment_id   text,
    order_id     text,
    created_at   text,
    amount       text,
    reason       text
);

CREATE TABLE IF NOT EXISTS raw.events (
    event_id     text,
    customer_id  text,
    name         text,
    occurred_at  text,
    properties   text
);

-- ---------------------------------------------------------------------------
-- Second product dimension: the subscription SaaS itself.
--
-- `raw.accounts` is what Stripe customers, PostHog groups and product signups
-- all resolve to. It is the join key the reconciliation model needs, and the
-- reason those three sources can be made to disagree with each other
-- convincingly instead of merely differing in spelling.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw.accounts (
    account_id     text,
    name           text,
    plan           text,
    seats          text,
    country        text,
    created_at     text,
    status         text,
    mrr            text,
    trial_ends_at  text,
    churned_at     text
);

-- ---------------------------------------------------------------------------
-- Stripe.
--
-- Landed the way Stripe actually hands data over: the verbatim webhook payload
-- in `payload`, with only `created_at` promoted to a column for querying. Every
-- field below `payload` is exactly as the API returns it, including the details
-- that are easy to get wrong and that make generated data believable:
-- integer amounts in the smallest currency unit, epoch-second timestamps,
-- lowercased ISO currency, and negative amounts on balance transactions.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw.stripe_customers (
    stripe_id   text,
    created_at  text,
    payload     text
);

CREATE TABLE IF NOT EXISTS raw.stripe_subscriptions (
    stripe_id          text,
    customer_id        text,
    status             text,
    created_at         text,
    current_period_end text,
    payload            text
);

CREATE TABLE IF NOT EXISTS raw.stripe_invoices (
    stripe_id      text,
    customer_id    text,
    subscription_id text,
    status         text,
    created_at     text,
    payload        text
);

CREATE TABLE IF NOT EXISTS raw.stripe_charges (
    charge_id    text,
    customer_id  text,
    status       text,
    currency     text,
    amount       text,
    created_at   text,
    payload      text
);

CREATE TABLE IF NOT EXISTS raw.stripe_refunds (
    refund_id   text,
    charge_id   text,
    created_at  text,
    amount      text,
    payload     text
);

CREATE TABLE IF NOT EXISTS raw.stripe_balance_transactions (
    txn_id      text,
    charge_id   text,
    type        text,
    created_at  text,
    amount      text,
    fee         text,
    net         text,
    payload     text
);

-- ---------------------------------------------------------------------------
-- PostHog.
--
-- PostHog's own event envelope: `event` plus `distinct_id` plus a `timestamp`
-- plus a free-form `properties` map. URL, referrer, browser and OS are promoted
-- to columns because they are the properties every real analysis filters on;
-- everything else, including the `$set` / `$set_once` person properties and the
-- feature-flag calls with their variant, stays inside `properties`.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw.posthog_people (
    distinct_id  text,
    created_at   text,
    properties   text
);

CREATE TABLE IF NOT EXISTS raw.posthog_events (
    event_id     text,
    event        text,
    distinct_id  text,
    occurred_at  text,
    current_url  text,
    referrer     text,
    browser      text,
    os           text,
    properties   text
);

CREATE TABLE IF NOT EXISTS raw.ga4_sessions (
    session_id           text,
    occurred_at          text,
    country              text,
    device_category      text,
    traffic_source       text,
    source_medium        text,
    campaign             text,
    session_number       text,
    engagement_time_msec text,
    is_bounce            text
);

-- The generator truncates before a full reseed, so a rebuild is idempotent.
CREATE OR REPLACE FUNCTION raw.truncate_all() RETURNS void AS $$
BEGIN
    TRUNCATE raw.customers, raw.products, raw.subscriptions, raw.orders,
             raw.order_items, raw.payments, raw.refunds, raw.events,
             raw.accounts,
             raw.stripe_customers, raw.stripe_subscriptions, raw.stripe_invoices,
             raw.stripe_charges, raw.stripe_refunds, raw.stripe_balance_transactions,
             raw.posthog_people, raw.posthog_events, raw.ga4_sessions;
END;
$$ LANGUAGE plpgsql;
