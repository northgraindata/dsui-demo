"""Integration assertions executed inside the running Airflow container."""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import base64

import duckdb
import pipeline


def request(path, payload=None):
    credentials = base64.b64encode((os.environ['AIRFLOW_API_USER']+':'+os.environ['AIRFLOW_API_PASSWORD']).encode()).decode()
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request('http://localhost:8080/api/v1/'+path, data=body,
                                 headers={'Authorization':'Basic '+credentials,'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def main():
    assert request('importErrors')['total_entries'] == 0
    for dag in ('demo_pipeline','daily_ecommerce_load'):
        run_id = 'smoke__'+datetime.now(timezone.utc).isoformat()
        request(f'dags/{dag}/dagRuns', {'dag_run_id':run_id})
        deadline = time.monotonic()+300
        while True:
            run = request(f'dags/{dag}/dagRuns/{run_id}')
            if run['state'] == 'success':
                break
            if run['state'] == 'failed' or time.monotonic() > deadline:
                raise AssertionError(f'{dag}: {run["state"]}')
            time.sleep(2)
        print(f'PASS real scheduler execution: {dag}', flush=True)
    snapshot = Path('/out/demo.duckdb')
    with duckdb.connect(str(snapshot), read_only=True) as connection:
        assert connection.execute("select count(*) from information_schema.tables where table_schema='landing' and table_type='BASE TABLE'").fetchone()[0] == 22
        assert connection.execute('select count(*) from marts.fct_revenue_daily').fetchone()[0] > 0
    keys = {row['Key'] for row in pipeline.storage().list_objects_v2(Bucket='landing')['Contents']}
    assert len([key for key in keys if '/' not in key]) == 43
    assert any(key.endswith('/daily_orders.parquet') for key in keys)
    before = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    marker = Path('/out/snapshot.json').read_bytes()
    # An empty landing directory must fail a genuine dbt build before publication.
    empty = Path('/out/ci/empty'); empty.mkdir(parents=True, exist_ok=True)
    os.environ['DEMO_LANDING_DIR'] = str(empty)
    os.environ['DEMO_DUCKDB_NEXT'] = '/out/ci/failed/demo.duckdb'
    try:
        pipeline.build_marts()
    except Exception as error:
        import subprocess
        assert isinstance(error, subprocess.CalledProcessError)
    else:
        raise AssertionError('Invalid dbt build unexpectedly succeeded')
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == before
    assert Path('/out/snapshot.json').read_bytes() == marker
    print('PASS S3 refresh, self-contained snapshot and failed-build preservation', flush=True)


if __name__ == '__main__':
    main()
