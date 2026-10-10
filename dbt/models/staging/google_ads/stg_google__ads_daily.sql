-- Google Ads daily report.
--
-- `cost_micros` is millionths of the account currency unit. Every other ad
-- platform reports spend as a decimal, so this is the column that makes a
-- cross-platform spend comparison wrong by a factor of a million if missed.

with source as (
    select date, campaign_id, campaign_name, impressions, clicks, cost_micros, conversions, conversions_value, ctr, average_cpc, average_cpm, all_conversions, cost_per_conversion, currency from {{ source('landing', 'google_ads_daily') }}
)

select
    try_strptime(date, '%Y-%m-%d')                                 as report_date,
    campaign_id,
    campaign_name,
    try_cast(impressions as bigint)                                as impressions,
    try_cast(clicks as bigint)                                     as clicks,
    try_cast(cost_micros as bigint)                                as cost_micros,
    cast(cost_micros as double) / 1000000.0                        as spend,
    try_cast(conversions as double)                                as conversions,
    cast(conversions_value as double)                              as conversions_value,
    try_cast(all_conversions as double)                            as all_conversions,
    cast(ctr as double)                                            as ctr,
    cast(average_cpc as double)                                    as cpc,
    cast(average_cpm as double)                                    as cpm,
    cast(cost_per_conversion as double)                            as cost_per_conversion,
    currency
from source
