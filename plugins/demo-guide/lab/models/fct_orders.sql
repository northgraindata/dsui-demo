-- The correction accepts both successful terminal statuses.
select order_id, ordered_on, status, amount
from read_parquet('{{ env_var("TOUR_ORDERS_PARQUET") }}')
where status in ('paid', 'completed')
