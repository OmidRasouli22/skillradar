-- Fails if a skill appears twice in the same role and region.
select role, region, skill
from {{ ref('gold_skill_demand') }}
group by role, region, skill
having count(*) > 1
