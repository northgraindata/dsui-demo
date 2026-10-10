select
    refund_id,
    payment_id,
    order_id,
    {{ parse_timestamp('created_at') }} as created_at,
    {{ parse_money('amount') }} as amount,
    reason
from {{ source('landing', 'refunds') }}
