-- Intentional regression for the developer tour: a new status is dropped.
-- Kept separate from the normal commerce marts.
select order_id, ordered_on, status, amount
from {{ source('tour_landing', 'demo_tour_orders') }}
where status = 'paid'
