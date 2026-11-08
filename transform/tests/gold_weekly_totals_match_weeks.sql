-- Fails if the weekly skill table and gold_weeks disagree on the tech postings of a week.
select w.week_start, w.tech_postings, s.total_postings
from {{ ref('gold_weeks') }} as w
join (
    select distinct week_start, total_postings
    from {{ ref('gold_skill_weekly') }}
    where role = 'all' and region = 'all'
) as s using (week_start)
where s.total_postings != w.tech_postings
