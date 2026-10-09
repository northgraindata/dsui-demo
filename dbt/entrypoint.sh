#!/usr/bin/env sh
# The build target lives in `next/` and keeps the file name it will have once
# published, because dbt-duckdb derives the attached catalog name from the
# file's stem. Airflow renames the file into place, so a visitor reading the
# previous snapshot never sees a half-built one.
set -eu

TARGET="${DEMO_DUCKDB_NEXT:-/out/next/demo.duckdb}"
mkdir -p "$(dirname "$TARGET")"

# Every build starts from nothing. dbt does not drop schemas it no longer
# manages, so reusing the file leaves renamed models behind as stale duplicates
# next to the current ones. Airflow only publishes on success, so a failed build
# leaving no file is the correct outcome rather than a lost one.
rm -f "$TARGET"

exec "$@"
