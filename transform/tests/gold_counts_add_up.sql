-- Fails if a count is impossible: more postings with a skill than in the group, or more
-- required than mentioned.
select *
from {{ ref('gold_skill_demand') }}
where required_postings > postings
   or postings > total_postings
   or share <= 0 or share > 1
