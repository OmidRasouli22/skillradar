-- How many open postings ask for each skill, per role and region.
-- A product name the posting does not contain was most likely made up by the model, so it
-- is left out. Concepts count even when the posting uses other words.

with scope as (
    select * from {{ ref('gold_scope') }}
),

totals as (
    select role, region, count(*) as total_postings
    from scope
    group by role, region
),

skills as (
    select refnr, skill, category, general, emerging, required
    from {{ ref('silver_posting_skills') }}
    where in_text or general
)

select
    scope.role,
    scope.region,
    skills.skill,
    skills.category,
    skills.general,
    skills.emerging,
    count(*) as postings,
    count(*) filter (where skills.required) as required_postings,
    totals.total_postings,
    round(count(*) / totals.total_postings, 4) as share
from scope
join skills using (refnr)
join totals using (role, region)
group by
    scope.role, scope.region, skills.skill, skills.category, skills.general, skills.emerging,
    totals.total_postings
