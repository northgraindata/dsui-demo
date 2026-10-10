select
    payload::json ->> 'id' as subscription_id,
    payload::json ->> 'customer' as customer_id,
    payload::json -> 'metadata' ->> 'account_id' as account_id,
    payload::json ->> 'status' as status,
    payload::json ->> 'currency' as currency,
    cast(to_timestamp((payload::json ->> 'created')::bigint) as timestamp) as created_at,
    cast(to_timestamp((payload::json ->> 'current_period_start')::bigint) as timestamp) as current_period_start,
    cast(to_timestamp((payload::json ->> 'current_period_end')::bigint) as timestamp) as current_period_end,
    cast(to_timestamp((payload::json ->> 'canceled_at')::bigint) as timestamp) as canceled_at,
    (payload::json ->> 'cancel_at_period_end')::boolean as cancel_at_period_end,
    (payload::json -> 'items' -> 'data' -> 0 -> 'price' ->> 'unit_amount')::integer as unit_amount_minor,
    (payload::json -> 'items' -> 'data' -> 0 ->> 'quantity')::integer as quantity,
    payload::json as payload
from {{ source('landing', 'stripe_subscriptions') }}
