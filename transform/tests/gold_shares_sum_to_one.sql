-- Fails if the values of an attribute do not cover every posting in a group exactly once.
select role, region, attribute, sum(postings) as postings, max(total_postings) as total
from {{ ref('gold_attribute_shares') }}
group by role, region, attribute
having sum(postings) != max(total_postings)
