select
    payment_id,
    order_id,
    method,
    {{ normalize_status('status') }} as status,
    {{ parse_money('amount') }} as amount,
    {{ parse_timestamp('captured_at') }} as captured_at,
    failure_reason
from {{ source('landing', 'payments') }}
