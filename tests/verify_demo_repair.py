"""Exercise the guide repair with the text-typed amounts found in its input."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ["DEMO_LANDING_DIR"]) / "demo_tour_orders.parquet"


def quote_sql_path(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


with tempfile.TemporaryDirectory(prefix="dsui-guide-test-") as directory:
    text_orders = Path(directory) / "orders-text.parquet"
    with duckdb.connect() as connection:
        connection.execute(
            "COPY (SELECT order_id, ordered_on, status, CAST(amount AS VARCHAR) AS amount "
            f"FROM read_parquet({quote_sql_path(SOURCE)})) "
            f"TO {quote_sql_path(text_orders)} (FORMAT PARQUET)"
        )

    environment = {
        **os.environ,
        "TOUR_ORDERS_PARQUET": str(text_orders),
        "DBT_EXECUTABLE": "dbt",
    }
    subprocess.run(
        [sys.executable, str(ROOT / "plugins/demo-guide/lab/repair.py")],
        check=True,
        env=environment,
    )
