select
    payload::json ->> 'id' as invoice_id,
    payload::json ->> 'customer' as customer_id,
    payload::json ->> 'subscription' as subscription_id,
    payload::json ->> 'charge' as charge_id,
    payload::json ->> 'status' as status,
    payload::json ->> 'currency' as currency,
    cast(to_timestamp((payload::json ->> 'created')::bigint) as timestamp) as created_at,
    (payload::json ->> 'amount_due')::integer as amount_due_minor,
    (payload::json ->> 'amount_paid')::integer as amount_paid_minor,
    (payload::json ->> 'amount_remaining')::integer as amount_remaining_minor,
    (payload::json ->> 'paid')::boolean as is_paid,
    payload::json as payload
from {{ source('landing', 'stripe_invoices') }}
