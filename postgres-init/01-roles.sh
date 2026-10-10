#!/usr/bin/env bash
set -euo pipefail
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=database="$POSTGRES_DB" --set=ON_ERROR_STOP=1 --set=airflow_user="$AIRFLOW_DB_USER" \
  --set=airflow_password="$AIRFLOW_DB_PASSWORD" --set=writer_user="$DEMO_WRITER_USER" \
  --set=writer_password="$DEMO_WRITER_PASSWORD" --set=reader_user="$DEMO_READER_USER" \
  --set=reader_password="$DEMO_READER_PASSWORD" <<'SQL'
CREATE ROLE :"airflow_user" LOGIN PASSWORD :'airflow_password';
CREATE DATABASE airflow OWNER :"airflow_user";
CREATE ROLE :"writer_user" LOGIN PASSWORD :'writer_password';
CREATE ROLE :"reader_user" LOGIN PASSWORD :'reader_password';
GRANT CREATE ON DATABASE :"database" TO :"writer_user";
CREATE SCHEMA raw AUTHORIZATION :"writer_user";
GRANT USAGE ON SCHEMA raw TO :"reader_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"writer_user" IN SCHEMA raw
    GRANT SELECT ON TABLES TO :"reader_user";
ALTER ROLE :"reader_user" SET default_transaction_read_only = on;
ALTER ROLE :"reader_user" SET statement_timeout = '30s';
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL
