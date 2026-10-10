# Runs the dbt build. Nothing here writes Postgres: DuckDB is dbt's engine and
# its output, and the landing zone is read-only Parquet.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    DBT_PROFILES_DIR=/dbt

WORKDIR /dbt

RUN pip install --no-cache-dir dbt-core==1.9.10 dbt-duckdb==1.9.2 duckdb==1.2.2

COPY dbt/dbt_project.yml dbt/profiles.yml dbt/packages.yml dbt/package-lock.yml ./
RUN dbt deps
COPY dbt/macros ./macros
COPY dbt/models ./models
COPY dbt/tests ./tests
COPY dbt/entrypoint.sh ./

ENTRYPOINT ["./entrypoint.sh"]
CMD ["dbt", "build"]
