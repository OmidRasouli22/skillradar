-- Fails if 'all' does not hold each open posting with an answer exactly once.
select refnr
from {{ ref('gold_scope') }}
where role = 'all' and region = 'all'
group by refnr
having count(*) != 1
