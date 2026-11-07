-- Fails if a weekly count is impossible: more postings with a skill than in the group,
-- more required than mentioned, or a group without postings.
select *
from {{ ref('gold_skill_weekly') }}
where required_postings > postings
   or postings > total_postings
   or total_postings <= 0
   or share < 0 or share > 1
