select
    order_id,
    sku,
    {{ parse_integer('quantity') }} as quantity,
    {{ parse_money('unit_price') }} as unit_price,
    {{ parse_money('discount') }} as discount
from {{ source('landing', 'order_items') }}
