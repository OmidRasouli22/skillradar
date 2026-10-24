-- Fails if dates in the history do not make sense.
select *
from {{ ref('silver_posting_history') }}
where first_seen > last_seen
   or closed_on <= last_seen
   or days_seen < 1
   or days_seen > last_seen - first_seen + 1
