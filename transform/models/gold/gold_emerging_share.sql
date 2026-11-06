-- How many open postings ask for at least one skill that only became mainstream in 2022
-- or later (LLMs, RAG, AI coding tools), per role and region. Same counting rules as
-- gold_skill_demand: a product the posting does not name is left out.

with scope as (
    select * from {{ ref('gold_scope') }}
),

totals as (
    select role, region, count(*) as total_postings
    from scope
    group by role, region
),

emerging as (
    select distinct refnr
    from {{ ref('silver_posting_skills') }}
    where emerging and (in_text or general)
)

select
    totals.role,
    totals.region,
    count(emerging.refnr) as postings,
    totals.total_postings,
    round(count(emerging.refnr) / totals.total_postings, 4) as share
from totals
left join scope using (role, region)
left join emerging on emerging.refnr = scope.refnr
group by totals.role, totals.region, totals.total_postings
