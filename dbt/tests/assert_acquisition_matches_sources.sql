-- Independent raw sums catch report fan-out and the wrong position formula.
with meta as (
    select cast(date as date) as report_date, sum(spend::double) as spend,
           sum(clicks::bigint) as clicks, sum(impressions::bigint) as impressions
    from {{ source('landing', 'meta_ads_daily') }} group by 1
), google as (
    select cast(date as date) as report_date, sum(cost_micros::bigint) / 1000000.0 as spend
    from {{ source('landing', 'google_ads_daily') }} group by 1
), search as (
    select cast(date as date) as report_date,
           round(sum(position::double * impressions::bigint) / nullif(sum(impressions::bigint), 0), 2) as position
    from {{ source('landing', 'gsc_daily') }} group by 1
)
select m.report_date
from {{ ref('fct_acquisition_daily') }} m
left join meta a using (report_date)
left join google g using (report_date)
left join search s using (report_date)
where abs(m.meta_spend - coalesce(a.spend, 0)) > 0.000001
   or m.meta_clicks <> coalesce(a.clicks, 0)
   or m.meta_impressions <> coalesce(a.impressions, 0)
   or abs(m.google_ads_spend - coalesce(g.spend, 0)) > 0.000001
   or m.average_position is distinct from s.position
