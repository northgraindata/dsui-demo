with daily as (
    select date_trunc('month', revenue_date)::date as month,
           sum(gross_minor) / 100.0 as gross,
           sum(refunded_minor) / 100.0 as refunded,
           sum(fees_minor) / 100.0 as fees,
           sum(net_minor) / 100.0 as net
    from {{ ref('fct_revenue_daily') }} where currency = 'eur' group by 1
)
select m.month
from {{ ref('fct_revenue_reconciliation') }} m
left join daily d using (month)
where abs(m.revenue_gross - coalesce(d.gross, 0)) > 0.000001
   or abs(m.revenue_refunded - coalesce(d.refunded, 0)) > 0.000001
   or abs(m.revenue_processing_fees - coalesce(d.fees, 0)) > 0.000001
   or abs(m.revenue_net - coalesce(d.net, 0)) > 0.000001
