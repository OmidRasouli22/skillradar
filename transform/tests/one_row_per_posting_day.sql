-- Fails if a posting appears twice on the same day.
select snapshot_date, refnr
from {{ ref('silver_posting_days') }}
group by snapshot_date, refnr
having count(*) > 1
