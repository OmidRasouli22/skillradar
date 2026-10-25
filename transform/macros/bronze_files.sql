{# Finished bronze files of one kind. Unfinished `.part` files are not matched. #}
{% macro bronze_files(kind, extension='jsonl') -%}
    '{{ env_var("SKILLRADAR_BRONZE_DIR") }}/{{ kind }}/snapshot_date=*/run_*.{{ extension }}'
{%- endmacro %}

{% macro bronze_run_logs() -%}
    '{{ env_var("SKILLRADAR_BRONZE_DIR") }}/runs/run_*.json'
{%- endmacro %}

{# Run ids look like 20261024T060000Z. The snapshot day is the UTC date of the run. #}
{% macro snapshot_date(run_id) -%}
    strptime(left({{ run_id }}, 8), '%Y%m%d')::date
{%- endmacro %}
