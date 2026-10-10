-- Signed impact on the merchant balance, in integer minor currency units.
select
    payload::json ->> 'id' as txn_id,
    charge_id,
    payload::json ->> 'source' as source_id,
    payload::json ->> 'type' as txn_type,
    cast(to_timestamp((payload::json ->> 'created')::bigint) as timestamp) as created_at,
    cast(to_timestamp((payload::json ->> 'available_on')::bigint) as timestamp) as available_on,
    (payload::json ->> 'amount')::integer as amount_minor,
    (payload::json ->> 'fee')::integer as fee_minor,
    (payload::json ->> 'net')::integer as net_minor,
    payload::json ->> 'currency' as currency,
    payload::json ->> 'status' as availability,
    payload::json ->> 'reporting_category' as reporting_category,
    payload::json as payload
from {{ source('landing', 'stripe_balance_transactions') }}
