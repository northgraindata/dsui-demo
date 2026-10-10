-- Meta Ads insights, one row per campaign per day.
--
-- `spend` is a decimal string and `actions` is the nested action-type/value array
-- the API returns. Splitting the array out into rows is the useful move: it makes
-- `purchase` a column you can sum instead of JSON you have to parse at query time.

with source as (
    select date, campaign_id, campaign_name, adset_id, adset_name, impressions, reach, clicks, spend, cpc, cpm, ctr, currency, actions from {{ source('landing', 'meta_ads_daily') }}
),

typed as (
    select
        try_strptime(date, '%Y-%m-%d')                            as report_date,
        campaign_id,
        campaign_name,
        adset_id,
        adset_name,
        try_cast(impressions as bigint)                           as impressions,
        try_cast(reach as bigint)                                 as reach,
        try_cast(clicks as bigint)                                as clicks,
        cast(spend as double)                                     as spend,
        cast(cpc as double)                                       as cpc,
        cast(cpm as double)                                       as cpm,
        cast(ctr as double)                                       as ctr,
        currency,
        actions
    from source
)

select
    * exclude (actions),
    actions::json as actions,
    coalesce((select sum((action.value ->> 'value')::double)
              from unnest(typed.actions::json[]) as action(value)
              where action.value ->> 'action_type' = 'purchase'), 0) as purchases
from typed
