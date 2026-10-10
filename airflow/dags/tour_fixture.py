"""A tiny, repeatable regression for the developer tour, separate from generated orders."""
import os
from pathlib import Path

import duckdb
import psycopg

ROWS = [
    ("tour-001", "2026-10-08", "paid", 100),
    ("tour-002", "2026-10-08", "paid", 120),
    ("tour-003", "2026-10-08", "paid", 80),
    ("tour-004", "2026-10-09", "paid", 90),
    ("tour-005", "2026-10-09", "completed", 110),
    ("tour-006", "2026-10-09", "completed", 100),
    ("tour-007", "2026-10-10", "completed", 100),
    ("tour-008", "2026-10-10", "completed", 120),
    ("tour-009", "2026-10-10", "completed", 80),
]


def extract():
    with psycopg.connect(os.environ["DATABASE_URL"]) as source:
        source.execute("create table if not exists raw.demo_tour_orders (order_id text primary key, ordered_on date not null, status text not null, amount integer not null)")
        with source.cursor() as cursor:
            cursor.executemany("insert into raw.demo_tour_orders values (%s,%s,%s,%s) on conflict (order_id) do update set ordered_on=excluded.ordered_on,status=excluded.status,amount=excluded.amount", ROWS)
        rows = source.execute("select order_id, ordered_on, status, amount from raw.demo_tour_orders order by order_id").fetchall()
    write_landing(rows, Path(os.environ.get("DEMO_LANDING_DIR", "/out/landing")))
    print(f"Developer tour: extracted {len(rows)} orders, including the new completed status")
    return len(rows)


def write_landing(rows, landing):
    landing.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as output:
        output.execute("create table orders(order_id varchar, ordered_on date, status varchar, amount integer)")
        output.executemany("insert into orders values (?,?,?,?)", rows)
        destination = str(landing / "demo_tour_orders.parquet").replace("'", "''")
        output.execute(f"copy orders to '{destination}' (format parquet)")
