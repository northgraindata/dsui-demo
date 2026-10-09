"""The demo's own data pipeline, as a customer would write it.

This is deliberately not the same thing as `demo_pipeline`. That DAG builds the
platform's warehouse and is infrastructure nobody should have to look at. This
one is the *customer's* pipeline: three tasks, a schedule, and a history, so the
Airflow service in the demo has something honest to show rather than the
platform's internal build log.

`catchup` with a past `start_date` is what fills that history. Airflow creates the
missed runs on its own once the scheduler is up, which is more robust than a
backfill step: it needs no extra command, no reset-dagruns dance, and it keeps
working when the instance is rebuilt.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="daily_ecommerce_load",
    description="Synthetic e-commerce source to warehouse, three stages",
    # Far enough back that the dashboard opens with real history rather than one
    # lonely run.
    start_date=pendulum.datetime(2026, 1, 5, 2, 0, tz="UTC"),
    schedule="0 2 * * *",
    catchup=True,
    max_active_runs=1,
    default_args={
        "owner": "data-platform",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["demo", "customer-pipeline"],
) as dag:
    extract = BashOperator(
        task_id="extract_orders",
        bash_command=(
            "echo 'extracting orders for ${ds}' && "
            # Reads the landing bucket, so the DAG reports on files that exist
            # rather than on a hardcoded list that drifts.
            "mc ls local/landing 2>/dev/null | wc -l || echo 'landing bucket not reachable from this task'"
        ),
    )

    transform = BashOperator(
        task_id="transform_orders",
        bash_command="echo 'transforming ${ds}' && sleep 2",
    )

    publish = BashOperator(
        task_id="publish_marts",
        bash_command="echo 'published marts for ${ds}'",
    )

    extract >> transform >> publish