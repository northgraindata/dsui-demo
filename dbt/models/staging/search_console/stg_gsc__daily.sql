-- Search Console search analytics.
--
-- One row per query and page combination per day, with a fractional average
-- position. Position is a mean over a range, not a rank, so a value of 4.3 means
-- "somewhere around fourth" and averaging it per day is meaningful while
-- averaging it per impression is not.

with source as (
    select date, query, page, country, device, search_appearance, clicks, impressions, ctr, position from {{ source('landing', 'gsc_daily') }}
)

select
    try_strptime(date, '%Y-%m-%d')                             as report_date,
    query,
    page,
    upper(trim(country))                                       as country,
    upper(trim(device))                                        as device,
    upper(nullif(trim(search_appearance), ''))                  as search_appearance,
    try_cast(clicks as bigint)                                 as clicks,
    try_cast(impressions as bigint)                            as impressions,
    cast(ctr as double)                                        as ctr,
    cast(position as double)                                   as position,
    -- Search Console's CTR is rounded to three decimals in the response.
    round(clicks::double / nullif(impressions::bigint, 0), 3)    as recomputed_ctr
from source
