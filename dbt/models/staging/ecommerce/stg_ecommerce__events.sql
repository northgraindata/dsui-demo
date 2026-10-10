select
    event_id,
    customer_id,
    name,
    {{ parse_timestamp('occurred_at') }} as occurred_at,
    properties::json as properties
from {{ source('landing', 'events') }}
