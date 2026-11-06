-- The skills each posting in gold_postings is counted for, with the same rule as
-- gold_skill_demand: a product the posting does not name is left out.

select k.refnr, k.skill, k.required, k.emerging
from {{ ref('silver_posting_skills') }} as k
join {{ ref('gold_postings') }} as p using (refnr)
where k.in_text or k.general
