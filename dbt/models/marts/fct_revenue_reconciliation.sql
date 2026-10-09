-- Monthly reconciliation: what each source claims, and why they disagree.
--
-- This is the model the whole dataset exists to support. A subscription business
-- has at least four defensible answers to "how much revenue did we make last
-- month", and a workspace that shows only one of them is hiding something. So
-- the mart keeps every answer side by side and names the gap.
--
-- The sources are not joined on identity. Stripe knows who paid, the product
-- database knows who is subscribed, PostHog knows who is active, and GA4 knows
-- who arrived without a name. They agree in shape and disagree in number, which
-- is the situation a real analyst actually has.
--
-- Read the variance columns as questions, not as errors. Most of them have a
-- boring answer, and the boring answer is the useful one.

with revenue as (
    -- Aggregated to the month here rather than joined on a truncated key.
    -- Leaving it daily made the join fan out to one row per day, so the model
    -- reported 286 rows for 23 months and each row carried a single day's
    -- revenue instead of the month's.
    select
        date_trunc('month', revenue_date)::date as month,
        sum(gross_minor)    / 100.0 as gross_revenue,
        sum(refunded_minor) / 100.0 as refunded,
        sum(fees_minor)     / 100.0 as processing_fees,
        sum(net_minor)      / 100.0 as net_revenue
    from {{ ref('fct_revenue_daily') }}
    where currency = 'eur'
    group by 1
),

stripe_billing as (
    select
        date_trunc('month', created_at)::date          as month,
        sum(case when status = 'paid' then 1 else 0 end) as paid_invoices,
        sum(case when status = 'open' then 1 else 0 end) as open_invoices,
        sum(case when status = 'draft' then 1 else 0 end) as draft_invoices
    from (
        select
            status,
            {{ parse_timestamp('created_at') }} as created_at
        from {{ source('landing', 'stripe_invoices') }}
    )
    group by 1
),

product_billing as (
    select
        date_trunc('month', created_at)::date       as month,
        count(*) filter (where lifecycle_status = 'active')    as active_accounts,
        count(*) filter (where lifecycle_status = 'churned')   as churned_accounts,
        count(*) filter (where lifecycle_status = 'trialing')  as trialing_accounts,
        sum(mrr) filter (where lifecycle_status = 'active')   as mrr_from_product_db
    from {{ ref('stg_accounts') }}
    group by 1
),

stripe_billing_counts as (
    select
        date_trunc('month', created_at)::date as month,
        count(*) filter (where lower(status) = 'active')   as active_subscriptions_stripe,
        count(*) filter (where lower(status) = 'canceled') as canceled_subscriptions_stripe,
        count(*) filter (where lower(status) = 'past_due') as past_due_subscriptions
    from (
        select
            lower(status) as status,
            {{ parse_timestamp('created_at') }} as created_at
        from {{ source('landing', 'stripe_subscriptions') }}
    )
    group by 1
),

acquisition as (
    select
        date_trunc('month', report_date)::date as month,
        sum(meta_spend)         as meta_spend,
        sum(google_ads_spend)   as google_ads_spend,
        sum(total_paid_spend)   as total_paid_spend,
        sum(total_clicks)       as total_clicks,
        sum(total_sessions)     as total_sessions,
        sum(organic_clicks)     as organic_clicks
    from {{ ref('fct_acquisition_daily') }}
    group by 1
),

engagement as (
    select
        date_trunc('month', occurred_at)::date as month,
        count(distinct distinct_id)                            as active_users,
        count(*) filter (where event = '$feature_flag_called') as feature_flag_calls,
        count(distinct account_id) filter (
            where event = '$feature_flag_called'
              and feature_flag_variant = 'treatment'
        )                                                   as accounts_seen_treatment
    from {{ ref('stg_posthog_events') }}
    group by 1
),

-- A spine of months, built from whichever sources have data.
--
-- Chained full outer joins were the obvious way to write this and were wrong:
-- the revenue side is daily while every other side is monthly, so joining on
-- the raw key matched a day against a month start, produced one row per day with
-- every other figure null, and fanned out into duplicates. A spine makes the
-- grain explicit and every join a simple left join on an already-monthly key.
month_spine as (
    -- `union` rather than `union all` plus a wrapping subquery, and every
    -- reference qualified. The spine column and each source column are all
    -- called `month`, and an unqualified `month` inside the set was ambiguous
    -- about which of them it meant.
    select revenue.month from revenue
    union select product_billing.month from product_billing
    union select stripe_billing_counts.month from stripe_billing_counts
    union select stripe_billing.month from stripe_billing
    union select acquisition.month from acquisition
    union select engagement.month from engagement
)

select
    m.month,

    -- What Stripe says.
    coalesce(r.gross_revenue, 0)    as revenue_gross,
    coalesce(r.refunded, 0)         as revenue_refunded,
    coalesce(r.processing_fees, 0)  as revenue_processing_fees,
    coalesce(r.net_revenue, 0)      as revenue_net,

    -- What the product database says.
    coalesce(p.active_accounts, 0)      as active_accounts_product_db,
    coalesce(p.churned_accounts, 0)     as churned_accounts,
    coalesce(p.trialing_accounts, 0)    as trialing_accounts,
    coalesce(p.mrr_from_product_db, 0)  as mrr_from_product_db,

    -- What Stripe's billing records say.
    coalesce(s.active_subscriptions_stripe, 0)  as active_subscriptions_stripe,
    coalesce(s.canceled_subscriptions_stripe, 0) as canceled_subscriptions_stripe,
    coalesce(s.past_due_subscriptions, 0) as past_due_subscriptions,
    coalesce(i.paid_invoices, 0)         as paid_invoices,
    coalesce(i.open_invoices, 0)         as open_invoices,
    coalesce(i.draft_invoices, 0)        as draft_invoices,

    -- What the acquisition reports say.
    coalesce(a.meta_spend, 0)       as meta_spend,
    coalesce(a.google_ads_spend, 0) as google_ads_spend,
    coalesce(a.total_paid_spend, 0) as total_paid_spend,
    coalesce(a.total_clicks, 0)     as total_clicks,
    coalesce(a.organic_clicks, 0)   as organic_clicks,
    coalesce(a.total_sessions, 0)   as total_sessions,

    -- What the product analytics say.
    coalesce(e.active_users, 0)            as active_users,
    coalesce(e.feature_flag_calls, 0)      as feature_flag_calls,
    coalesce(e.accounts_seen_treatment, 0) as accounts_seen_treatment,

    -- The gaps, named rather than left for someone to notice.
    coalesce(p.active_accounts, 0) - coalesce(s.active_subscriptions_stripe, 0)
        as active_account_gap,
    coalesce(r.gross_revenue, 0) - coalesce(p.mrr_from_product_db, 0)
        as revenue_vs_mrr_gap,
    round(
        100.0 * coalesce(r.processing_fees, 0) / nullif(r.gross_revenue, 0), 2
    ) as effective_fee_pct,
    round(
        100.0 * (coalesce(p.active_accounts, 0) - coalesce(s.active_subscriptions_stripe, 0))
        / nullif(coalesce(s.active_subscriptions_stripe, 0), 0), 2
    ) as account_gap_pct,

    -- A plain-language reading of the largest discrepancy in the row.
    case
        when coalesce(p.active_accounts, 0) > coalesce(s.active_subscriptions_stripe, 0)
            then 'product database counts accounts Stripe has no active subscription for'
        when coalesce(p.active_accounts, 0) < coalesce(s.active_subscriptions_stripe, 0)
            then 'Stripe holds subscriptions the product database does not recognise'
        when coalesce(i.open_invoices, 0) > 0
            then 'revenue differs because invoices are still open or past due'
        else 'sources agree on active accounts'
    end as largest_discrepancy

from month_spine m
left join revenue             r on r.month = m.month
left join product_billing     p on p.month = m.month
left join stripe_billing_counts s on s.month = m.month
left join stripe_billing      i on i.month = m.month
left join acquisition         a on a.month = m.month
left join engagement          e on e.month = m.month
