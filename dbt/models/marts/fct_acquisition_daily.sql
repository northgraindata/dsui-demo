-- One row per UTC report day, combining EUR spend and anonymous sessions.
-- Meta retains its report grain; the purchase array never multiplies spend.
-- Source reports share EUR, so no synthetic FX conversion is needed.

with meta as (
    select
        report_date,
        sum(purchases)  as meta_purchases,
        sum(spend)                                                           as spend,
        sum(clicks)                                                          as clicks,
        sum(impressions)                                                     as impressions
    from {{ ref('stg_meta__ads_daily') }}
    group by 1
),

google as (
    select
        report_date,
        sum(spend)             as spend,
        sum(clicks)            as clicks,
        sum(impressions)       as impressions,
        sum(conversions)       as conversions,
        sum(conversions_value) as conversions_value
    from {{ ref('stg_google__ads_daily') }}
    group by 1
),

gsc as (
    select
        report_date,
        sum(clicks)      as clicks,
        sum(impressions) as impressions,
        sum(position * impressions::double) as position_weighted_impressions
    from {{ ref('stg_gsc__daily') }}
    group by 1
),

sessions as (
    select
        session_date,
        sum(case when medium in ('cpc', 'paid_social') then 1 else 0 end) as paid_sessions,
        sum(case when medium in ('organic', 'referral') then 1 else 0 end) as organic_sessions,
        count(*)                                                          as total_sessions
    from {{ ref('stg_ga4__sessions') }}
    group by 1
)

select
    coalesce(m.report_date, g.report_date, o.report_date, s.session_date) as report_date,

    coalesce(m.spend, 0)                     as meta_spend,
    coalesce(m.clicks, 0)                    as meta_clicks,
    coalesce(m.impressions, 0)               as meta_impressions,
    coalesce(m.meta_purchases, 0)            as meta_purchases,

    coalesce(g.spend, 0)                     as google_ads_spend,
    coalesce(g.clicks, 0)                    as google_ads_clicks,
    coalesce(g.impressions, 0)               as google_ads_impressions,
    coalesce(g.conversions, 0)               as google_ads_conversions,
    coalesce(g.conversions_value, 0)         as google_ads_conversions_value,

    coalesce(o.clicks, 0)                    as organic_clicks,
    coalesce(o.impressions, 0)               as organic_impressions,
    -- Weight position by impressions to match Search Console aggregation.
    round(coalesce(o.position_weighted_impressions, 0)
          / nullif(coalesce(o.impressions, 0), 0), 2) as average_position,

    coalesce(s.paid_sessions, 0)             as paid_sessions,
    coalesce(s.organic_sessions, 0)          as organic_sessions,
    coalesce(s.total_sessions, 0)            as total_sessions,

    coalesce(m.spend, 0) + coalesce(g.spend, 0)                        as total_paid_spend,
    coalesce(m.clicks, 0) + coalesce(g.clicks, 0) + coalesce(o.clicks, 0) as total_clicks

from meta m
full outer join google g on g.report_date = m.report_date
full outer join gsc o     on o.report_date = coalesce(m.report_date, g.report_date)
full outer join sessions s on s.session_date = coalesce(m.report_date, g.report_date, o.report_date)
