-- Airflow keeps its own metadata database, separate from the demo's analytics
-- one, so an Airflow migration can never touch demo data. Created here because
-- POSTGRES_DB only initialises a single database.
CREATE DATABASE airflow;
