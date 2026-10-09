-- Stripe charges.
--
-- The payload is the source of truth; the promoted columns are an index into it.
-- Amounts are integer minor units in the API's own currency, which is why
-- nothing here divides by a hundred: that belongs in a mart, once, where the
-- currency is known.

with source as (
    select
        charge_id,
        customer_id,
        status,
        currency,
        amount,
        created_at,
        payload
    from {{ source('landing', 'stripe_charges') }}
),

parsed as (
    select
        charge_id,
        customer_id,
        {{ normalize_status('status') }}              as status,
        lower(trim(currency))                        as currency,
        {{ parse_integer('amount') }}                as amount_minor,
        {{ parse_timestamp('created_at') }}          as created_at,
        (payload::json ->> 'captured')::boolean      as is_captured,
        (payload::json ->> 'paid')::boolean          as is_paid,
        (payload::json -> 'refunded')::boolean       as is_refunded,
        try_cast(payload::json ->> 'amount_refunded' as integer) as amount_refunded_minor,
        payload::json -> 'outcome' ->> 'risk_level'  as risk_level,
        try_cast(payload::json -> 'outcome' ->> 'risk_score' as integer) as risk_score,
        payload::json -> 'payment_method_details' -> 'card' ->> 'brand' as card_brand,
        payload::json -> 'payment_method_details' -> 'card' ->> 'last4' as card_last4,
        payload::json -> 'payment_method_details' -> 'card' ->> 'country' as card_country,
        payload::json -> 'billing_details' -> 'address' ->> 'country' as billing_country,
        payload::json ->> 'balance_transaction'      as balance_transaction_id,
        payload::json ->> 'payment_intent'           as payment_intent_id,
        payload::json -> 'metadata' ->> 'account_id' as account_id,
        payload::json ->> 'failure_code'             as failure_code,
        payload
    from source
)

select * from parsed
