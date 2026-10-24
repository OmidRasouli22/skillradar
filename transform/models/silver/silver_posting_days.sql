-- One row per posting and day it was open. Base for day-by-day history.

select distinct snapshot_date, refnr
from {{ ref('stg_search_sightings') }}
