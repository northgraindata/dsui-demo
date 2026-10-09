-- PostHog people, carrying `$set` and `$set_once`.
--
-- `$set` properties are mutable and `$set_once` are not, which is exactly the
-- distinction dbt has to preserve: a re-identified property is an update, not a
-- duplicate row to drop.

with source as (
    select * from {{ source('landing', 'posthog_people') }}
)

select
    distinct_id,
    {{ parse_timestamp('created_at') }}                  as created_at,
    {{ json_text('properties', '$."$set"."account_id"') }}        as account_id,
    {{ json_text('properties', '$."$set"."account_plan"') }}      as account_plan,
    try_cast({{ json_text('properties', '$."$set"."seats"') }} as integer) as seats,
    upper({{ json_text('properties', '$."$set_once"."country"') }})       as country,
    lower({{ json_text('properties', '$."$set_once"."signup_source"') }}) as signup_source,
    {# Jinja parses its own grammar, so a SQL expression such as
       `properties::json -> '$set_once'` has to arrive as a quoted string
       rather than as a bare macro argument. The macros interpolate verbatim. #}
    {{ parse_timestamp("json_extract_string(properties::json, '$.\"$set_once\".\"created_at\"')") }} as signed_up_at
from source
