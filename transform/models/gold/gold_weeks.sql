-- One row per week (Monday to Sunday) with snapshots: how many days have data, and how
-- many of the postings open that week have an answer from Claude (coverage).
-- Postings that closed before they were sent to Claude never got an answer, so the first
-- weeks have a lower coverage. Apprenticeships are not sent to Claude and not counted.

with days as (
    select
        date_trunc('week', d.snapshot_date)::date as week_start,
        d.snapshot_date,
        d.refnr,
        e.refnr is not null as answered,
        e.role is not null and e.role != 'not_tech' as tech
    from {{ ref('silver_posting_days') }} as d
    left join {{ ref('silver_postings') }} as p using (refnr)
    left join {{ ref('silver_posting_extractions') }} as e using (refnr)
    where p.posting_type is distinct from 'AUSBILDUNG'
),

weeks as (
    select
        week_start,
        count(distinct snapshot_date) as snapshot_days,
        count(distinct refnr) as open_postings,
        count(distinct refnr) filter (where answered) as answered_postings,
        count(distinct refnr) filter (where tech) as tech_postings
    from days
    group by week_start
)

select
    week_start,
    (week_start + 6)::date as week_end,
    snapshot_days,
    -- A week is over once there is data from its Sunday or later.
    week_start + 6 <= (select max(snapshot_date) from days) as week_ended,
    open_postings,
    answered_postings,
    tech_postings,
    round(answered_postings / open_postings, 4) as coverage
from weeks
