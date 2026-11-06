-- Open tech postings with an answer from Claude, once per role and region, plus 'all'.
-- A posting with places in two regions counts in each of them, and once in 'all'.
-- The search also finds some jobs that are not tech work (role not_tech); they are left out.

with postings as (
    select e.refnr, e.role
    from {{ ref('silver_posting_extractions') }} as e
    join {{ ref('silver_posting_history') }} as h using (refnr)
    where h.is_open and e.role != 'not_tech'
),

regions as (
    select distinct l.refnr, l.region
    from {{ ref('silver_posting_locations') }} as l
    join postings as p using (refnr)
    where l.region is not null
    union all
    select refnr, 'all' from postings
),

roles as (
    select refnr, role from postings
    union all
    select refnr, 'all' from postings
)

select roles.refnr, roles.role, regions.region
from roles
join regions using (refnr)
