"""Initialize the demo before exposing the scheduler and authenticated API."""
import os
import subprocess
import time
from pathlib import Path

from airflow.www.app import create_app

import pipeline


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
    deadline = time.monotonic() + 600
    while not Path('/out/seed-ready.json').exists():
        if time.monotonic() >= deadline:
            raise TimeoutError('Generator did not complete the initial seed within 10 minutes')
        time.sleep(2)
    pipeline.run('bootstrap')
    os.execvp('airflow', ['airflow', 'standalone'])


if __name__ == '__main__':
    main()
