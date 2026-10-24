-- Newest details record per posting. Postings that were gone (details = null) are left out.

with raw as (
    select run_id, refnr, details
    from read_json(
        {{ bronze_files('details') }},
        format = 'newline_delimited',
        columns = {run_id: 'VARCHAR', refnr: 'VARCHAR', details: 'JSON'},
        ignore_errors = true
    )
)

select run_id, refnr, details
from raw
where refnr is not null
  and json_type(details) = 'OBJECT'
qualify row_number() over (partition by refnr order by run_id desc) = 1
