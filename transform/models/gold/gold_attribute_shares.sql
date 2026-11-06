-- Seniority, home office and language levels of open postings, per role and region.
-- A language the posting does not ask for counts as 'not asked'.

with scope as (
    select * from {{ ref('gold_scope') }}
),

totals as (
    select role, region, count(*) as total_postings
    from scope
    group by role, region
),

postings as (
    select refnr, seniority, remote from {{ ref('silver_posting_extractions') }}
),

languages as (
    select refnr, language, level from {{ ref('silver_posting_languages') }}
),

answer_values as (
    select refnr, 'seniority' as attribute, seniority as value from postings
    union all
    select refnr, 'remote', remote from postings
    union all
    select p.refnr, 'german', coalesce(l.level, 'not asked')
    from postings as p
    left join languages as l on l.refnr = p.refnr and l.language = 'German'
    union all
    select p.refnr, 'english', coalesce(l.level, 'not asked')
    from postings as p
    left join languages as l on l.refnr = p.refnr and l.language = 'English'
)

select
    scope.role,
    scope.region,
    answer_values.attribute,
    answer_values.value,
    count(*) as postings,
    totals.total_postings,
    round(count(*) / totals.total_postings, 4) as share
from scope
join answer_values using (refnr)
join totals using (role, region)
group by scope.role, scope.region, answer_values.attribute, answer_values.value,
    totals.total_postings
