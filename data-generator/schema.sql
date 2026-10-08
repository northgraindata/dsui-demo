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

-- The generator truncates before a full reseed, so a rebuild is idempotent.
CREATE OR REPLACE FUNCTION raw.truncate_all() RETURNS void AS $$
BEGIN
    TRUNCATE raw.customers, raw.products, raw.subscriptions, raw.orders,
             raw.order_items, raw.payments, raw.refunds, raw.events;
END;
$$ LANGUAGE plpgsql;
