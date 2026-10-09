# Runs the dbt build. Nothing here writes Postgres: DuckDB is dbt's engine and
# its output, and the landing zone is read-only Parquet.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    DBT_PROFILES_DIR=/dbt

WORKDIR /dbt

RUN pip install --no-cache-dir dbt-duckdb==1.9.2

COPY dbt_project.yml profiles.yml ./
COPY macros ./macros
COPY models ./models
COPY tests ./tests
COPY entrypoint.sh ./

ENTRYPOINT ["./entrypoint.sh"]
CMD ["dbt", "build"]
