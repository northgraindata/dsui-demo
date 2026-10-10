select
    order_id,
    customer_id,
    {{ parse_timestamp('placed_at') }} as placed_at,
    {{ normalize_status('status') }} as status,
    upper(trim(currency)) as currency,
    {{ parse_money('total') }} as total,
    channel,
    coupon_code
from {{ source('landing', 'orders') }}
