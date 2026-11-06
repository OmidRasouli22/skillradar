-- The cleaned text (contact details removed) of each posting in gold_postings.

select t.refnr, t.description
from {{ ref('silver_posting_texts') }} as t
join {{ ref('gold_postings') }} as p using (refnr)
