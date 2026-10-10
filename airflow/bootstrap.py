"""Initialize the demo before exposing the scheduler and authenticated API."""
import json
import os
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

from airflow.www.app import create_app


def _airflow_healthy() -> bool:
    with urllib.request.urlopen('http://localhost:8080/health', timeout=2) as response:
        report = json.load(response)
    return (report.get('metadatabase', {}).get('status') == 'healthy'
            and report.get('scheduler', {}).get('status') == 'healthy')


def _wait_for(predicate, message, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except (OSError, KeyError, ValueError):
            pass
        time.sleep(2)
    raise TimeoutError(message)


def main():
    subprocess.run(['airflow', 'db', 'migrate'], check=True)
    app = create_app()
    with app.app_context():
        manager = app.appbuilder.sm
        username = os.environ['AIRFLOW_API_USER']
        user = manager.find_user(username=username)
        if user is None:
            user = manager.add_user(username, 'Demo', 'Operator', 'demo@example.invalid',
                                    manager.find_role('Admin'), os.environ['AIRFLOW_API_PASSWORD'])
            if not user:
                raise RuntimeError('Could not provision the demo Airflow user')
        else:
            manager.reset_password(user.id, os.environ['AIRFLOW_API_PASSWORD'])

    _wait_for(lambda: Path('/out/seed-ready.json').exists(),
              'Generator did not complete the initial seed within 10 minutes', 600)

    # Bring the webserver and scheduler up before the first snapshot is built, so
    # the healthcheck passes while the initial build is still running instead of
    # only after it. The build itself runs through the scheduler, sharing the
    # DAG's single-run serialization rather than racing a scheduled run.
    airflow = subprocess.Popen(['airflow', 'standalone'])

    def _forward_shutdown(_signum, _frame):
        airflow.terminate()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _forward_shutdown)
    signal.signal(signal.SIGINT, _forward_shutdown)

    try:
        _wait_for(_airflow_healthy, 'Airflow did not become healthy within 10 minutes', 600)
        subprocess.run(['airflow', 'dags', 'trigger', 'demo_pipeline'], check=True)
        _wait_for(lambda: Path('/out/demo.duckdb').is_file() and Path('/out/snapshot.json').is_file(),
                  'Pipeline did not publish a snapshot within 15 minutes', 900)
        airflow.wait()
    except BaseException:
        if airflow.poll() is None:
            airflow.terminate()
        raise


if __name__ == '__main__':
    main()
