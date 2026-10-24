-- Fails if an email address is left in a cleaned description.
select refnr
from {{ ref('silver_posting_texts') }}
where regexp_matches(description, '[\w.+-]+@[\w-]+\.[\w-]+')
