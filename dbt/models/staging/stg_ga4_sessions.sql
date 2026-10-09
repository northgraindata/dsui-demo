-- GA4 sessions.
--
-- Anonymous by design. There is no account key on this table and there never
-- will be, which is precisely why it cannot be joined to Stripe or PostHog at
-- the session level. The mart reconciles on aggregates, not on identity.

with source as (
    select * from {{ source('landing', 'ga4_sessions') }}
)

select
    session_id,
    {{ parse_timestamp('occurred_at') }}                          as occurred_at,
    date({{ parse_timestamp('occurred_at') }})                    as session_date,
    upper(trim(country))                                          as country,
    lower(trim(device_category))                                  as device_category,
    lower(trim(traffic_source))                                   as traffic_source,
    lower(trim(source_medium))                                    as source_medium,
    nullif(trim(campaign), '(not set)')                           as campaign_name,
    try_cast({{ parse_integer('session_number') }} as integer)    as session_number,
    try_cast({{ parse_integer('engagement_time_msec') }} as integer) as engagement_time_msec,
    try_cast({{ parse_integer('is_bounce') }} as integer)         as is_bounce,
    split_part(source_medium, '/', 1)                             as source,
    trim(split_part(source_medium, '/', 2))                       as medium
from source
