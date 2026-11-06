-- Fails if a posting has the same skill twice.
select refnr, skill
from {{ ref('silver_posting_skills') }}
group by refnr, skill
having count(*) > 1
