-- Which postings each run saw. One row per run and posting.

select distinct
    run_id,
    {{ snapshot_date('run_id') }} as snapshot_date,
    posting ->> 'referenznummer' as refnr
from read_json(
    {{ bronze_files('search', 'jsonl.gz') }},
    format = 'newline_delimited',
    columns = {run_id: 'VARCHAR', posting: 'JSON'},
    ignore_errors = true
)
where posting ->> 'referenznummer' is not null
