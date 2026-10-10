"""The same extract/build/publish functions run on first boot and in Airflow."""
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import boto3
import psycopg

import extract
import tour_fixture

NEXT_DB = Path(os.environ.get('DEMO_DUCKDB_NEXT', '/out/next/demo.duckdb'))
PUBLISHED_DB = Path(os.environ.get('DEMO_DUCKDB_PUBLISHED', '/out/demo.duckdb'))


def storage():
    return boto3.client('s3', endpoint_url=os.environ['S3_ENDPOINT'],
                        aws_access_key_id=os.environ['S3_ACCESS_KEY'],
                        aws_secret_access_key=os.environ['S3_SECRET_KEY'],
                        region_name='eu-central-1')


def extract_landing():
    counts = extract.run()
    if len(counts) != 21 or any(count == 0 for count in counts.values()):
        raise RuntimeError(f'Incomplete landing extraction: {counts}')
    tour_fixture.extract()
    return counts


def build_marts():
    subprocess.run(['/dbt/entrypoint.sh', 'dbt', 'build', '--project-dir', '/dbt',
                    '--profiles-dir', '/dbt'], check=True,
                   env={**os.environ, 'PATH':'/opt/dbt/bin:'+os.environ['PATH']})


def publish_snapshot(run_id):
    if not NEXT_DB.is_file():
        raise RuntimeError(f'dbt produced no snapshot at {NEXT_DB}')
    # Raw data is materialized inside DuckDB, so a renamed snapshot is self-contained.
    client = storage()
    try:
        client.head_bucket(Bucket='landing')
    except client.exceptions.ClientError as error:
        if error.response['ResponseMetadata']['HTTPStatusCode'] != 404:
            raise
        client.create_bucket(Bucket='landing')
    for path in sorted(extract.LANDING_DIR.iterdir()):
        if path.suffix in ('.csv', '.parquet'):
            client.upload_file(str(path), 'landing', path.name)
    os.replace(NEXT_DB, PUBLISHED_DB)
    marker = PUBLISHED_DB.parent / 'snapshot.json'
    temporary = marker.with_suffix('.json.tmp')
    temporary.write_text(json.dumps({'published_at':datetime.now(timezone.utc).isoformat(),
                                     'dag_run':run_id})+'\n')
    temporary.replace(marker)


def run(run_id):
    # Serializes bootstrap and operational rebuilds even outside the scheduler.
    with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True) as lock:
        lock.execute('select pg_advisory_lock(4192001)')
        extract_landing()
        build_marts()
        publish_snapshot(run_id)
