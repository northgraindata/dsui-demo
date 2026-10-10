select
    payload::json ->> 'id' as customer_id,
    cast(to_timestamp((payload::json ->> 'created')::bigint) as timestamp) as created_at,
    payload::json ->> 'name' as name,
    payload::json ->> 'email' as email,
    payload::json -> 'metadata' ->> 'account_id' as account_id,
    (payload::json ->> 'delinquent')::boolean as is_delinquent,
    payload::json ->> 'currency' as currency,
    payload::json as payload
from {{ source('landing', 'stripe_customers') }}
