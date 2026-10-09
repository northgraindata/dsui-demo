# Airflow and the pipeline it orchestrates in one container.
#
# extract, dbt and publish share a process boundary on purpose: DuckDB allows one
# writer, so handing the file between containers would mean coordinating a lock
# for no benefit. Airflow runs them in order and the rename at the end is the
# only thing a visitor can observe.

FROM apache/airflow:2.10.5-python3.12

ARG AIRFLOW_VERSION=2.10.5

RUN pip install --no-cache-dir \
    "apache-airflow==${AIRFLOW_VERSION}" \
    "apache-airflow-providers-postgres==5.14.0" \
    "dbt-duckdb==1.9.2" \
    "pyarrow==18.1.0" \
    "psycopg[binary]==3.2.3"

ENV AIRFLOW__CORE__LOAD_EXAMPLES=False \
    AIRFLOW__CORE__EXECUTOR=LocalExecutor \
    AIRFLOW__SCHEDULING__MIN_FILE_PROCESS_INTERVAL=30 \
    AIRFLOW__API_AUTH__JWT_SECRET=${AIRFLOW_JWT_SECRET:-dsui-demo-jwt-secret} \
    DBT_PROFILES_DIR=/dbt \
    DEMO_LANDING_DIR=/out \
    DEMO_DUCKDB_NEXT=/out/next/demo.duckdb \
    DEMO_DUCKDB_PUBLISHED=/out/demo.duckdb \
    DEMO_DBT_PROJECT=/dbt

WORKDIR /airflow
