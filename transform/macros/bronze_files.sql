{# Finished bronze files of one kind. Unfinished `.part` files are not matched. #}
{% macro bronze_files(kind) -%}
    '{{ env_var("SKILLRADAR_BRONZE_DIR") }}/{{ kind }}/snapshot_date=*/run_*.jsonl'
{%- endmacro %}
