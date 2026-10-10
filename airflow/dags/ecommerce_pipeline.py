"""A real daily commerce load: PostgreSQL orders to validated aggregates in S3."""
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

import commerce

with DAG(
    dag_id='daily_ecommerce_load',
    description='Extract daily orders, validate totals and publish Parquet to object storage',
    start_date=pendulum.datetime(2026, 1, 5, 2, tz='UTC'),
    schedule='0 2 * * *',
    catchup=False,
    max_active_runs=1,
    default_args={'owner':'data-platform','retries':2,'retry_delay':timedelta(minutes=2)},
    tags=['demo','customer-pipeline'],
) as dag:
    extract_orders = PythonOperator(task_id='extract_orders', python_callable=commerce.extract_orders)
    transform_orders = PythonOperator(task_id='transform_orders', python_callable=commerce.transform_orders)
    publish_orders = PythonOperator(task_id='publish_marts', python_callable=commerce.publish_orders)
    extract_orders >> transform_orders >> publish_orders
