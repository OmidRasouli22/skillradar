-- The federal states a posting lists, once per posting and state. A posting with places in
-- two states belongs to both. Places without a state are left out.

select distinct refnr, region
from {{ ref('silver_posting_locations') }}
where region is not null
