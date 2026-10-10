select
    customer_id,
    nullif(trim(email), '') as email,
    full_name,
    upper(trim(country)) as country,
    {{ parse_timestamp('signup_at') }} as signup_at,
    {{ normalize_status('plan') }} as plan,
    {{ parse_money('mrr') }} as mrr,
    is_trial::boolean as is_trial,
    referred_by::boolean as referred_by,
    {{ parse_timestamp('last_seen_at') }} as last_seen_at
from {{ source('landing', 'customers') }}
where customer_id not like '%-DUP'
