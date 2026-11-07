-- Fails if a skill appears twice in the same week, role and region.
select week_start, role, region, skill
from {{ ref('gold_skill_weekly') }}
group by week_start, role, region, skill
having count(*) > 1
