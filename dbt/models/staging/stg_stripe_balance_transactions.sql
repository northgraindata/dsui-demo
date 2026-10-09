-- Balance transactions, which is where the money actually lands.
--
-- `amount` is signed against the account: a charge is negative, a refund is
-- positive. `net` is what reaches the bank after the processor fee. A revenue
-- mart built from charges and one built from this table will differ by exactly
-- that fee, which is the reconciliation the demo is built to show.

with source as (
    select * from {{ source('landing', 'stripe_balance_transactions') }}
)

select
    txn_id,
    charge_id,
    {{ normalize_status('type') }}                    as txn_type,
    {{ parse_timestamp('created_at') }}              as created_at,
    {{ parse_integer('amount') }}                    as amount_minor,
    {{ parse_integer('fee') }}                       as fee_minor,
    {{ parse_integer('net') }}                       as net_minor,
    payload::json ->> 'currency'                     as currency,
    payload::json ->> 'status'                       as availability,
    payload::json ->> 'reporting_category'           as reporting_category,
    payload::json ->> 'type'                         as raw_type
from source
