-- One row per open tech posting with an answer from Claude: the facts the job list and
-- the job view show. The place is the first one the posting lists. A few postings have
-- no title; they show their occupation instead.

with postings as (
    select distinct refnr from {{ ref('gold_scope') }}
),

first_place as (
    select refnr, city, region
    from {{ ref('silver_posting_locations') }}
    where position = 1
),

languages as (
    select refnr, language, level from {{ ref('silver_posting_languages') }}
)

select
    p.refnr,
    coalesce(s.title, s.occupation, 'Job posting') as title,
    s.employer,
    s.first_published,
    e.role,
    e.seniority,
    e.remote,
    l.city,
    l.region,
    coalesce(german.level, 'not asked') as german,
    coalesce(english.level, 'not asked') as english
from postings as p
join {{ ref('silver_postings') }} as s using (refnr)
join {{ ref('silver_posting_extractions') }} as e using (refnr)
left join first_place as l using (refnr)
left join languages as german on german.refnr = p.refnr and german.language = 'German'
left join languages as english on english.refnr = p.refnr and english.language = 'English'
