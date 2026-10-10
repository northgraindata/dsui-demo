-- Intentional regression for the developer tour: a new status is dropped.
-- Kept separate from the normal commerce marts.
select order_id, ordered_on, status, amount
from {{ ref('stg_tour__orders') }}
where status = 'paid'
