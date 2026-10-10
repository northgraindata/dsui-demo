select
    payload::json ->> 'id' as refund_id,
    payload::json ->> 'charge' as charge_id,
    payload::json ->> 'balance_transaction' as balance_transaction_id,
    payload::json ->> 'payment_intent' as payment_intent_id,
    payload::json ->> 'currency' as currency,
    payload::json ->> 'status' as status,
    payload::json ->> 'reason' as reason,
    (payload::json ->> 'amount')::integer as amount_minor,
    cast(to_timestamp((payload::json ->> 'created')::bigint) as timestamp) as created_at,
    payload::json as payload
from {{ source('landing', 'stripe_refunds') }}
