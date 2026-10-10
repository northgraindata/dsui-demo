select
    subscription_id,
    customer_id,
    {{ normalize_status('plan') }} as plan,
    {{ normalize_status('status') }} as status,
    {{ parse_integer('seats') }} as seats,
    {{ parse_money('mrr') }} as mrr,
    {{ parse_timestamp('started_at') }} as started_at,
    {{ parse_timestamp('ended_at') }} as ended_at
from {{ source('landing', 'subscriptions') }}
