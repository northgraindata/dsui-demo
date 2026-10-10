# Airflow and the pipeline it orchestrates in one container.
#
# extract, dbt and publish share a process boundary on purpose: DuckDB allows one
# writer, so handing the file between containers would mean coordinating a lock
# for no benefit. Airflow runs them in order and the rename at the end is the
# only thing a visitor can observe.

FROM apache/airflow:2.10.5-python3.12

# dbt and Airflow require incompatible protobuf ranges; keep separate environments.
USER root
RUN python -m venv /opt/dbt && chown -R airflow:root /opt/dbt
USER airflow
RUN pip install --no-cache-dir duckdb==1.2.2 pyarrow==18.1.0 "psycopg[binary]==3.2.3" boto3==1.36.3
RUN /opt/dbt/bin/pip install --no-cache-dir dbt-core==1.9.10 dbt-duckdb==1.9.2 duckdb==1.2.2

ENV AIRFLOW__CORE__LOAD_EXAMPLES=False \
    AIRFLOW__CORE__EXECUTOR=LocalExecutor \
    AIRFLOW__CORE__DAGS_FOLDER=/opt/demo/dags \
    DBT_PROFILES_DIR=/dbt \
    DEMO_LANDING_DIR=/out/landing \
    DEMO_DUCKDB_NEXT=/out/next/demo.duckdb \
    DEMO_DUCKDB_PUBLISHED=/out/demo.duckdb \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    PYTHONPATH=/opt/demo/dags

COPY --chown=airflow:root dbt /dbt
RUN /opt/dbt/bin/dbt deps --project-dir /dbt --profiles-dir /dbt
COPY --chown=airflow:root airflow /opt/demo
CMD ["python", "/opt/demo/bootstrap.py"]
