-- Skill demand per week, role and region: the history for trends and forecasts.
-- A posting counts in each week it was open on at least one day. Roles, regions and skills
-- are counted like in gold_scope and gold_skill_demand.
-- A skill a group ever asked for has a row in every week the group had postings, with 0
-- when no posting asked for it, so each series has no gaps. Check the week's coverage in
-- gold_weeks before comparing weeks.

with postings as (
    select distinct date_trunc('week', d.snapshot_date)::date as week_start, d.refnr, e.role
    from {{ ref('silver_posting_days') }} as d
    join {{ ref('silver_posting_extractions') }} as e using (refnr)
    join {{ ref('silver_postings') }} as p using (refnr)
    where e.role != 'not_tech' and p.posting_type is distinct from 'AUSBILDUNG'
),

roles as (
    select week_start, refnr, role from postings
    union all
    select week_start, refnr, 'all' from postings
),

regions as (
    select r.refnr, r.region
    from {{ ref('silver_posting_regions') }} as r
    where r.refnr in (select refnr from postings)
    union all
    select distinct refnr, 'all' from postings
),

scope as (
    select roles.week_start, roles.refnr, roles.role, regions.region
    from roles
    join regions using (refnr)
),

totals as (
    select week_start, role, region, count(*) as total_postings
    from scope
    group by week_start, role, region
),

skills as (
    select refnr, skill, category, general, emerging, required
    from {{ ref('silver_posting_skills') }}
    where in_text or general
),

counts as (
    select
        scope.week_start,
        scope.role,
        scope.region,
        skills.skill,
        count(*) as postings,
        count(*) filter (where skills.required) as required_postings
    from scope
    join skills using (refnr)
    group by scope.week_start, scope.role, scope.region, skills.skill
),

series as (
    select distinct role, region, skill from counts
),

skill_info as (
    select distinct skill, category, general, emerging from skills
)

select
    totals.week_start,
    totals.role,
    totals.region,
    series.skill,
    skill_info.category,
    skill_info.general,
    skill_info.emerging,
    coalesce(counts.postings, 0) as postings,
    coalesce(counts.required_postings, 0) as required_postings,
    totals.total_postings,
    round(coalesce(counts.postings, 0) / totals.total_postings, 4) as share
from totals
join series using (role, region)
join skill_info using (skill)
left join counts using (week_start, role, region, skill)
