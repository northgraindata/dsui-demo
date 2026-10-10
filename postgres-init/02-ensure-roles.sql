\getenv database POSTGRES_DB
\getenv airflow_database AIRFLOW_DB_NAME
\getenv airflow_user AIRFLOW_DB_USER
\getenv airflow_password AIRFLOW_DB_PASSWORD
\getenv writer_user DEMO_WRITER_USER
\getenv writer_password DEMO_WRITER_PASSWORD
\getenv reader_user DEMO_READER_USER
\getenv reader_password DEMO_READER_PASSWORD

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'airflow_user', :'airflow_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'airflow_user')
\gexec
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'airflow_user', :'airflow_password')
\gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'airflow_database', :'airflow_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'airflow_database')
\gexec

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'writer_user', :'writer_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'writer_user')
\gexec
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'writer_user', :'writer_password')
\gexec

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'reader_user', :'reader_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'reader_user')
\gexec
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'reader_user', :'reader_password')
\gexec

SELECT format('GRANT CREATE ON DATABASE %I TO %I', :'database', :'writer_user')
\gexec
SELECT format('CREATE SCHEMA IF NOT EXISTS raw AUTHORIZATION %I', :'writer_user')
\gexec
SELECT format('ALTER SCHEMA raw OWNER TO %I', :'writer_user')
\gexec
SELECT format('GRANT USAGE ON SCHEMA raw TO %I', :'reader_user')
\gexec
SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA raw GRANT SELECT ON TABLES TO %I',
  :'writer_user',
  :'reader_user'
)
\gexec
SELECT format('ALTER ROLE %I SET default_transaction_read_only = on', :'reader_user')
\gexec
SELECT format('ALTER ROLE %I SET statement_timeout = %L', :'reader_user', '30s')
\gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
