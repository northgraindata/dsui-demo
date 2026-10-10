-- Both the charge and the refund must point back to the actual ledger entry.
select b.txn_id
from {{ ref('stg_stripe__balance_transactions') }} b
left join {{ ref('stg_stripe__charges') }} c on b.source_id = c.charge_id and b.txn_type = 'charge'
left join {{ ref('stg_stripe__refunds') }} r on b.source_id = r.refund_id and b.txn_type = 'refund'
where (b.txn_type = 'charge' and (
           c.charge_id is null or not c.is_paid or not c.is_captured
           or b.amount_minor <> c.amount_minor
           or b.currency <> c.currency or b.created_at <> c.created_at
           or b.txn_id <> c.balance_transaction_id))
   or (b.txn_type = 'refund' and (
           r.refund_id is null or b.amount_minor <> -r.amount_minor
           or b.currency <> r.currency or b.created_at <> r.created_at
           or b.txn_id <> r.balance_transaction_id))
