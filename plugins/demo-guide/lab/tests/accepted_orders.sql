-- The deterministic fixture has nine orders and 900 total revenue.
select 1 as unexpected_result
where (select count(*) from {{ ref('fct_orders') }}) <> 9
   or (select sum(amount) from {{ ref('fct_orders') }}) <> 900
