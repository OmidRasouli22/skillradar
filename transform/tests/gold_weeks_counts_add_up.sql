-- Fails if a week's counts are impossible.
select *
from {{ ref('gold_weeks') }}
where answered_postings > open_postings
   or tech_postings > answered_postings
   or snapshot_days not between 1 and 7
   or coverage < 0 or coverage > 1
   or week_end != week_start + 6
   or isodow(week_start) != 1
