select order_id, ordered_on, status, amount
from {{ source('tour_landing', 'demo_tour_orders') }}
