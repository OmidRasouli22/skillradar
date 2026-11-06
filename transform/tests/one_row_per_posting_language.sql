-- Fails if a posting has the same language twice.
select refnr, language
from {{ ref('silver_posting_languages') }}
group by refnr, language
having count(*) > 1
