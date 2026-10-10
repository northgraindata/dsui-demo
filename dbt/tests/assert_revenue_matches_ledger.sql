with ledger as (
    select cast(created_at as date) as revenue_date, currency, sum(net_minor) as net_minor
    from {{ ref('stg_stripe__balance_transactions') }}
    where availability = 'available' group by 1, 2
)
select coalesce(l.revenue_date, m.revenue_date) as revenue_date,
       coalesce(l.currency, m.currency) as currency
from ledger l
full outer join {{ ref('fct_revenue_daily') }} m using (revenue_date, currency)
where l.net_minor is distinct from m.net_minor
