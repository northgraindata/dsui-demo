select
    sku,
    name,
    category,
    {{ parse_money('price') }} as price,
    {{ parse_money('cost') }} as cost,
    {{ parse_timestamp('launched_at') }} as launched_at
from {{ source('landing', 'products') }}
