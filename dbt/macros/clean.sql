{#
    The cleaning macros.

    The generator writes every timestamp in one of five formats and every money
    value as a decorated string, on purpose. These are the SQL counterparts of
    the generator's `parse_timestamp` and `parse_money`, and they are the reason
    the staging layer exists at all: type inference cannot be trusted on a
    column that is `text` in five different shapes, and any attempt to fix that
    at the source would remove the only interesting work in the pipeline.
#}

{% macro parse_timestamp(column_name) -%}
    coalesce(
        try_strptime({{ column_name }}, '%Y-%m-%d %H:%M:%S'),
        try_strptime({{ column_name }}, '%d/%m/%Y %H:%M'),
        try_strptime({{ column_name }}, '%Y-%m-%dT%H:%M:%S'),
        {#- ISO with microseconds. Python's `isoformat()` emits them whenever the
            value has a fractional part, which was 14% of the Stripe timestamps
            and left them silently unparsed. -#}
        try_strptime({{ column_name }}, '%Y-%m-%dT%H:%M:%S.%f'),
        try_strptime({{ column_name }}, '%Y-%m-%dT%H:%M:%S.%fZ'),
        try_strptime({{ column_name }}, '%Y-%m-%dT%H:%M:%SZ'),
        try_strptime({{ column_name }}, '%Y-%m-%d'),
        {# epoch seconds, which arrive as a bare integer string #}
        case
            when regexp_matches(trim({{ column_name }}), '^[0-9]{9,}$')
            then cast(to_timestamp(try_cast({{ column_name }} as bigint)) as timestamp)
        end
    )
{%- endmacro %}


{% macro parse_money(column_name) -%}
    {% set cleaned = "regexp_replace(trim(" ~ column_name ~ "), '[^0-9,.-]', '', 'g')" %}
    case
        when {{ column_name }} is null or trim({{ column_name }}) = '' then null
        when contains({{ cleaned }}, ',') and contains({{ cleaned }}, '.')
        then cast(replace({{ cleaned }}, ',', '') as double)
        when contains({{ cleaned }}, ',')
        then cast(replace({{ cleaned }}, ',', '.') as double)
        else cast({{ cleaned }} as double)
    end
{%- endmacro %}


{% macro parse_integer(column_name) -%}
    {# Numbers that arrive as text with stray whitespace, or with separators. #}
    case
        when {{ column_name }} is null or trim({{ column_name }}) = '' then null
        else cast(replace(trim({{ column_name }}), ',', '') as integer)
    end
{%- endmacro %}


{% macro normalize_status(column_name) -%}
    {#- Case drifts between upstream systems; "Paid", "PAID" and "paid" are one value. -#}
    lower(trim({{ column_name }}))
{%- endmacro %}

{#-
    Reads a JSON value as text.

    PostHog property names start with `$`, and DuckDB reads a leading `$` in the
    `->>` operator as the JSONPath root rather than as part of the key. So
    `$feature_flag` fails to parse as a path instead of returning the value, and
    every `$`-prefixed key needs an explicit JSONPath with the segment quoted.

    The path is passed through verbatim rather than assembled from a dotted key.
    Building it hid the quoting that makes it work, which is the opposite of
    useful when the failure is a JSON path parse error.
-#}
{% macro json_text(column_name, json_path) -%}
    json_extract_string({{ column_name }}, '{{ json_path }}')
{%- endmacro %}


{% macro json_number(column_name, json_path) -%}
    try_cast({{ json_text(column_name, json_path) }} as bigint)
{%- endmacro %}


{% macro json_double(column_name, json_path) -%}
    try_cast({{ json_text(column_name, json_path) }} as double)
{%- endmacro %}