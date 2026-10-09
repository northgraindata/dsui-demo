"""The demo pipeline.

    Postgres raw -> Parquet landing -> dbt -> next/demo.duckdb -> demo.duckdb

The order is not cosmetic. DuckDB permits a single writing process, so dbt
cannot build into the file a visitor is reading. It builds into `next/`, and the
publish step renames that file into place only after the build and its tests
pass. POSIX rename is atomic, so a visitor mid-read keeps the snapshot they
opened and the next visitor gets the new one. Nobody ever sees a half-built
warehouse, and a failed run leaves the previous snapshot serving.

The extract step is not redundant with the generator's own Parquet export. The
generator writes a snapshot when it seeds, while the generator is also appending
to Postgres every few minutes, so the landing zone is stale between builds and
the extract is what makes a run see current data.
"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

import extract

log = logging.getLogger(__name__)

LANDING_DIR = Path(os.environ.get("DEMO_LANDING_DIR", "/out"))
NEXT_DB = Path(os.environ.get("DEMO_DUCKDB_NEXT", "/out/next/demo.duckdb"))
PUBLISHED_DB = Path(os.environ.get("DEMO_DUCKDB_PUBLISHED", "/out/demo.duckdb"))
DBT_PROJECT = Path(os.environ.get("DEMO_DBT_PROJECT", "/dbt"))
MARKER = LANDING_DIR / "snapshot.json"


def extract_landing(**context) -> None:
    counts = extract.run()
    total = sum(counts.values())
    log.info("extracted %d rows across %d tables", total, len(counts))


def publish_snapshot(**context) -> None:
    """Moves the freshly built database into place.

    If the rename target cannot be replaced, the newly built file is left where
    it is rather than deleted: it is the only evidence of what went wrong, and
    the previously published snapshot is still serving.
    """
    if not NEXT_DB.exists():
        raise RuntimeError(f"dbt produced no database at {NEXT_DB}")

    PUBLISHED_DB.parent.mkdir(parents=True, exist_ok=True)
    previous = PUBLISHED_DB.with_suffix(".duckdb.previous")

    if PUBLISHED_DB.exists():
        shutil.copy2(PUBLISHED_DB, previous)
    os.replace(NEXT_DB, PUBLISHED_DB)

    MARKER.write_text(
        f'{{"published_at": "{datetime.now(timezone.utc).isoformat()}", '
        f'"dag_run": "{context["run_id"]}"}}\n',
        encoding="utf-8",
    )
    size_mb = PUBLISHED_DB.stat().st_size / 1_048_576
    log.info("published %s (%.1f MiB) for run %s", PUBLISHED_DB, size_mb, context["run_id"])


def summarise(**context) -> None:
    """Logs the reconciliation head, so the DAG log shows the business numbers.

    A visitor watching the pipeline sees when it ran and whether it worked. This
    makes the log also show what the run concluded, which is the part a person
    is actually looking for.
    """
    import duckdb

    if not PUBLISHED_DB.exists():
        log.warning("no published snapshot to summarise")
        return

    connection = duckdb.connect(str(PUBLISHED_DB), read_only=True)
    try:
        rows = connection.execute(
            """
            select month,
                   round(revenue_gross) as gross,
                   round(revenue_net)   as net,
                   round(mrr_from_product_db) as mrr,
                   active_accounts_product_db  as accounts,
                   active_subscriptions_stripe  as subscriptions,
                   largest_discrepancy
            from marts.fct_revenue_reconciliation
            order by month desc
            limit 3
            """
        ).fetchall()
    finally:
        connection.close()

    for row in rows:
        log.info(
            "%s gross=%s net=%s mrr=%s accounts=%s subscriptions=%s (%s)",
            *row,
        )


with DAG(
    dag_id="demo_pipeline",
    description="Postgres to Parquet to dbt to a published DuckDB snapshot",
    schedule="*/30 * * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    # Only one run may touch the DuckDB file at a time, and the publish step is
    # a rename that has to be the last thing to happen.
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
        "owner": "demo",
    },
    tags=["demo"],
) as dag:
    extract_task = PythonOperator(
        task_id="extract_landing",
        python_callable=extract_landing,
    )

    build_task = BashOperator(
        task_id="build_marts",
        bash_command=(
            f"cd {DBT_PROJECT} && dbt build "
            f"--project-dir {DBT_PROJECT} --profiles-dir {DBT_PROJECT}"
        ),
    )

    publish_task = PythonOperator(
        task_id="publish_snapshot",
        python_callable=publish_snapshot,
    )

    summarise_task = PythonOperator(
        task_id="summarise",
        python_callable=summarise,
    )

    extract_task >> build_task >> publish_task >> summarise_task