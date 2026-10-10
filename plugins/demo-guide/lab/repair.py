"""Build and test only this plugin's repair project in a disposable directory."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import duckdb

project = Path(__file__).parent
with tempfile.TemporaryDirectory(prefix="dsui-tour-") as work:
    isolated = Path(work) / "project"
    shutil.copytree(project, isolated, ignore=shutil.ignore_patterns("target", "logs", "__pycache__"))
    database = Path(work) / "repair.duckdb"
    environment = {**os.environ, "TOUR_REPAIR_DATABASE": str(database), "TOUR_ORDERS_PARQUET": "/out/landing/demo_tour_orders.parquet", "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
    build = subprocess.run(["/opt/dbt/bin/dbt", "build", "--project-dir", str(isolated), "--profiles-dir", str(isolated)], capture_output=True, text=True, env=environment, timeout=90)
    if build.returncode:
        raise RuntimeError("Isolated dbt build failed: " + build.stdout[-2000:] + build.stderr[-1000:])
    with duckdb.connect(str(database), read_only=True) as connection:
        orders, revenue = connection.execute("select count(*),sum(amount) from tour.fct_orders").fetchone()
    if (orders, revenue) != (9, 900):
        raise RuntimeError("Repair did not restore all nine orders and 900 revenue")
    print(json.dumps({"orders": orders, "revenue": revenue, "tests": "passed", "isolated": True}))
