-- PostHog events, flattened from the envelope.
--
-- `properties` stays as json because that is the shape the product sends. The
-- promoted columns are the ones every real analysis filters on, and
-- `feature_flag_variant` is null for everything except flag calls, which is
-- what makes a variant comparison honest rather than diluted by all other events.

with source as (
    select * from {{ source('landing', 'posthog_events') }}
)

select
    event_id,
    event,
    distinct_id,
    {{ parse_timestamp('occurred_at') }}                          as occurred_at,
    nullif(current_url, '')                                       as current_url,
    nullif(referrer, '')                                          as referrer,
    browser,
    os,
    properties,
    {{ json_text('properties', '$."$feature_flag"') }}                    as feature_flag,
    {{ json_text('properties', '$."$feature_flag_variant"') }}            as feature_flag_variant,
    {{ json_text('properties', '$."$groups"."account"') }}                as account_id,
    {{ json_number('properties', 'rows_synced') }}                as rows_synced,
    {{ json_number('properties', 'duration_ms') }}                as duration_ms,
    {{ json_number('properties', 'rows_returned') }}              as rows_returned,
    {{ json_text('properties', '$."$set"."account_plan"') }}    as account_plan_at_event
from source
