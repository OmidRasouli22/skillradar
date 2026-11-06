-- Fails unless gold_meta has exactly one row.
select count(*) as n from {{ ref('gold_meta') }} having count(*) != 1
