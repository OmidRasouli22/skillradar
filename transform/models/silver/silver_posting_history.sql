-- First and last day each posting was seen, and when it closed.
-- Only complete days can close a posting: a run with status ok that searched everything.
-- On other days a missing posting may only have been missed.

with seen as (
    select
        refnr,
        min(snapshot_date) as first_seen,
        max(snapshot_date) as last_seen,
        count(*) as days_seen
    from {{ ref('silver_posting_days') }}
    group by refnr
),

complete_days as (
    select distinct snapshot_date
    from {{ ref('stg_runs') }}
    where status = 'ok' and full_scope
),

closed as (
    select seen.refnr, min(complete_days.snapshot_date) as closed_on
    from seen
    join complete_days on complete_days.snapshot_date > seen.last_seen
    group by seen.refnr
)

select
    seen.refnr,
    seen.first_seen,
    seen.last_seen,
    seen.days_seen,
    closed.closed_on,
    closed.closed_on is null as is_open
from seen
left join closed on closed.refnr = seen.refnr
