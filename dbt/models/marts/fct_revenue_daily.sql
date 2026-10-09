-- Daily revenue, per currency, from the Stripe balance ledger.
--
-- Built from `balance_transactions` rather than `charges` on purpose. Gross
-- charges are not revenue: they exclude refunds and ignore the processing fee,
-- and a mart built the other way disagrees with this one by exactly the fee.
-- Both numbers exist in `fct_revenue_reconciliation` so the gap is inspectable
-- instead of argued about.

with transactions as (
    select * from {{ ref('stg_stripe_balance_transactions') }}
    where availability = 'available'
),

daily as (
    select
        cast(created_at as date)        as revenue_date,
        currency,
        txn_type,
        sum(amount_minor)              as amount_minor,
        sum(fee_minor)                 as fee_minor,
        sum(net_minor)                 as net_minor,
        count(*)                       as transaction_count
    from transactions
    group by 1, 2, 3
)

-- Signs are the whole subtlety here. A balance transaction is signed against
-- the account: a charge is negative and a refund is positive. Revenue reads
-- from the other side of the ledger, so charges are negated to become positive
-- gross, refunds keep their sign to become a positive amount returned, and the
-- fee stays positive as a cost. Getting this backwards yields revenue that is
-- negative and refunds that are negative, which is exactly what it did.
select
    revenue_date,
    currency,
    sum(case when txn_type = 'charge' then -amount_minor else 0 end)     as gross_minor,
    sum(case when txn_type = 'refund' then amount_minor else 0 end)      as refunded_minor,
    sum(case when txn_type = 'charge' then fee_minor else 0 end)          as fees_minor,
    -- Net revenue is gross less fees, plus refunds. It is deliberately not read
    -- from the ledger's own `net`, because Stripe defines that as
    -- `net = amount - fee` on a *negative* amount, so negating it to get a
    -- business figure adds the fee instead of subtracting it and produced net
    -- revenue above gross. The two definitions are both correct for their own
    -- purpose; only one of them is revenue.
    sum(
        case when txn_type = 'charge' then -amount_minor - fee_minor else amount_minor end
    ) as net_minor,
    sum(case when txn_type = 'charge' then transaction_count else 0 end) as charge_count,
    sum(case when txn_type = 'refund' then transaction_count else 0 end) as refund_count,
    -- Stored in minor units, because dividing by 100 here would silently break
    -- for any currency that is not two-decimal. The demo uses EUR, USD and GBP,
    -- all two-decimal, and the mart says so rather than assuming.
    'EUR'                                                                 as presentation_currency
from daily
group by 1, 2
