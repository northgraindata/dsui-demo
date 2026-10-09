"""Extracts the raw schema from PostgreSQL into the Parquet landing zone.

The column list comes from `information_schema` rather than from a table here.
A hardcoded list drifts: a table added to the generator is written to the landing
zone on seed, but a list living here would not learn about it, and the pipeline
would quietly ignore it. Reading the schema means there is nothing to keep in
sync.

Runs in the same container as dbt, between the two, and writes to a temporary
name before renaming into place so a concurrent reader never sees a partial file.
"""

from __future__ import annotations

import os
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import psycopg

LANDING_DIR = Path(os.environ.get("DEMO_LANDING_DIR", "/out"))
BATCH_SIZE = 20_000


def raw_tables(connection) -> list[tuple[str, list[str]]]:
    """Every table in `raw`, with its columns in ordinal order."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select table_name, column_name
            from information_schema.columns
            where table_schema = 'raw'
            order by table_name, ordinal_position
            """
        )
        tables: dict[str, list[str]] = {}
        for table, column in cursor.fetchall():
            tables.setdefault(table, []).append(column)
    return sorted(tables.items())


def extract_table(connection, table: str, columns: list[str]) -> int:
    """Streams one table to Parquet. Returns the row count."""
    path = LANDING_DIR / f"{table}.parquet"
    temporary = path.with_suffix(".parquet.tmp")
    schema = pa.schema([(name, pa.string()) for name in columns])
    projection = ", ".join(f'"{name}"' for name in columns)
    written = 0

    writer = pq.ParquetWriter(temporary, schema, compression="zstd")
    try:
        with connection.cursor() as cursor:
            with cursor.copy(
                f"COPY (select {projection} from raw.{table}) TO STDOUT"
            ) as copy:
                batch: list[tuple] = []
                for row in copy:
                    batch.append(tuple("" if value is None else value for value in row))
                    if len(batch) >= BATCH_SIZE:
                        written += _write_batch(writer, schema, columns, batch)
                        batch = []
                if batch:
                    written += _write_batch(writer, schema, columns, batch)
    except BaseException:
        writer.close()
        temporary.unlink(missing_ok=True)
        raise
    else:
        writer.close()
        temporary.replace(path)
    return written


def _write_batch(writer, schema, columns: list[str], batch: list[tuple]) -> int:
    arrays = [
        pa.array([row[index] for row in batch], type=pa.string())
        for index in range(len(columns))
    ]
    writer.write_table(pa.Table.from_arrays(arrays, schema=schema))
    return len(batch)


def run() -> dict[str, int]:
    LANDING_DIR.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        for table, columns in raw_tables(connection):
            counts[table] = extract_table(connection, table, columns)
    return counts