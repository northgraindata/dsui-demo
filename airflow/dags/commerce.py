"""Actual daily order extraction, aggregation and publication for the tour DAG."""
import json
import os
from pathlib import Path

import duckdb
import psycopg

import extract
import pipeline


def workspace(day):
    # Airflow's ds value is a date, not an arbitrary path segment.
    from datetime import date
    date.fromisoformat(day)
    path = Path('/out/commerce') / day
    path.mkdir(parents=True, exist_ok=True)
    return path


def extract_orders(ds, **_):
    path = workspace(ds)
    # Source exports contain ISO, DD/MM/YYYY and epoch timestamps.
    moment = """case when placed_at ~ '^[0-9]{9,}$'
        then to_timestamp(placed_at::bigint) at time zone 'UTC'
        when strpos(placed_at, '/') > 0 then to_timestamp(placed_at, 'DD/MM/YYYY HH24:MI') at time zone 'UTC'
        else placed_at::timestamp end"""
    with psycopg.connect(os.environ['DATABASE_URL']) as connection:
        extract.extract_table(connection, 'orders', [
            'order_id','customer_id','placed_at','status','currency','total','channel','coupon_code'
        ], directory=path, where=f'({moment})::date = %s::date', parameters=(ds,))


def transform_orders(ds, **_):
    path = workspace(ds)
    with duckdb.connect() as connection:
        connection.execute('create table orders as select * from read_parquet(?)', [str(path/'orders.parquet')])
        connection.execute("""create table daily_orders as
            select currency, lower(trim(status)) as status, count(*) as order_count,
                   sum(cast(case when contains(total, ',') and not contains(total, '.')
                       then replace(regexp_replace(total, '[^0-9,.-]', '', 'g'), ',', '.')
                       else replace(regexp_replace(total, '[^0-9,.-]', '', 'g'), ',', '')
                   end as decimal(18,2))) as order_total
            from orders group by 1,2""")
        connection.table('daily_orders').write_parquet(str(path/'daily_orders.parquet'), compression='zstd')
        rows = connection.execute('select sum(order_count) from daily_orders').fetchone()[0] or 0
        expected = connection.execute('select count(*) from orders').fetchone()[0]
        if rows != expected:
            raise RuntimeError('Aggregation lost or duplicated orders')
    (path/'summary.json').write_text(json.dumps({'day':ds,'orders':rows})+'\n')


def publish_orders(ds, **_):
    path = workspace(ds)
    client = pipeline.storage()
    for name in ('daily_orders.parquet','summary.json'):
        client.upload_file(str(path/name), 'landing', f'commerce/{ds}/{name}')
