with refunds as (
    select charge_id, sum(amount_minor) as amount_minor
    from {{ ref('stg_stripe__refunds') }} where status = 'succeeded' group by 1
)
select c.charge_id
from {{ ref('stg_stripe__charges') }} c
left join refunds r using (charge_id)
where c.amount_refunded_minor <> coalesce(r.amount_minor, 0)
   or c.amount_refunded_minor > c.amount_minor
   or (c.status = 'succeeded' and
       case when c.is_refunded then 1 else 0 end <>
       case when coalesce(r.amount_minor, 0) = c.amount_minor then 1 else 0 end)
