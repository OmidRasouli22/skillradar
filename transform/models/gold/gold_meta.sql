-- One row about the data behind the gold tables, for the page footer.
-- Apprenticeships are not sent to Claude, so they are not counted as open postings here.

select
    (
        select max(snapshot_date)
        from {{ ref('stg_runs') }}
        where status in ('ok', 'partial')
    ) as as_of,
    (
        select count(*)
        from {{ ref('silver_posting_history') }} as h
        join {{ ref('silver_postings') }} as p using (refnr)
        where h.is_open and p.posting_type is distinct from 'AUSBILDUNG'
    ) as open_postings,
    (
        select count(*)
        from {{ ref('silver_posting_extractions') }} as e
        join {{ ref('silver_posting_history') }} as h using (refnr)
        where h.is_open
    ) as postings_with_answers,
    (
        select count(*) from {{ ref('gold_scope') }} where role = 'all' and region = 'all'
    ) as tech_postings,
    (select max(model) from {{ ref('silver_posting_extractions') }}) as model,
    (select max(prompt_version) from {{ ref('silver_posting_extractions') }}) as prompt_version
