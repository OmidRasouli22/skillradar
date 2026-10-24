-- Status and scope of each run. Old logs without full_scope count as not full.

select
    run_id,
    {{ snapshot_date('run_id') }} as snapshot_date,
    status,
    coalesce(full_scope, false) as full_scope
from read_json(
    {{ bronze_run_logs() }},
    columns = {run_id: 'VARCHAR', status: 'VARCHAR', full_scope: 'BOOLEAN'}
)
where run_id is not null
