-- Settled cash movement per UTC day and currency, not accrual revenue.
select
    cast(created_at as date) as revenue_date,
    currency,
    sum(case when txn_type = 'charge' then amount_minor else 0 end) as gross_minor,
    sum(case when txn_type = 'refund' then -amount_minor else 0 end) as refunded_minor,
    sum(fee_minor) as fees_minor,
    sum(net_minor) as net_minor,
    count(*) filter (where txn_type = 'charge') as charge_count,
    count(*) filter (where txn_type = 'refund') as refund_count
from {{ ref('stg_stripe__balance_transactions') }}
where availability = 'available'
group by 1, 2
