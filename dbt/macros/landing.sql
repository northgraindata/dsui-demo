{# Materialize every Parquet file so a published snapshot is self-contained. #}

{% macro landing_views() %}
    {% if execute %}

        {% set landing_dir = env_var('DEMO_LANDING_DIR', '/out') %}

        {% do run_query('create schema if not exists landing') %}

        {% set files = run_query("select file from glob('" ~ landing_dir ~ "/*.parquet')") %}
        {% if files.rows | length == 0 %}
            {% do exceptions.raise_compiler_error(
                "no parquet files in " ~ landing_dir ~ "; run the generator seed or the Airflow extract first"
            ) %}
        {% endif %}

        {% for row in files.rows %}
            {% set path = row[0] %}
            {% set table = path.split('/')[-1].replace('.parquet', '') %}
            {% do run_query(
                "create or replace table landing." ~ table ~ " as select * from read_parquet('" ~ path ~ "')"
            ) %}
        {% endfor %}

        {% do log('landing: ' ~ (files.rows | length) ~ ' raw tables loaded from ' ~ landing_dir, info=false) %}

    {% endif %}
{% endmacro %}


{#
    Schema naming, so the schemas read as `landing`, `staging` and `marts`.

    The dbt default concatenates the target schema with the model's custom
    schema, which with `schema: marts` in the profile produced `marts_marts` and
    `marts_staging`. A visitor browsing the published database should not have to
    know that dbt has a default.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
