-- Fails if a posting has the same location position twice.
select refnr, position
from {{ ref('silver_posting_locations') }}
group by refnr, position
having count(*) > 1
