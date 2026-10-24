-- One row per posting and location. A posting can list up to 10 places.

with locations as (
    select
        refnr,
        json_extract(details, '$.stellenlokationen[*]') as places
    from {{ ref('stg_details') }}
),

numbered as (
    select
        refnr,
        generate_subscripts(places, 1) as position,
        unnest(places) as place
    from locations
)

select
    refnr,
    position,
    -- "Nürnberg, Mittelfranken" -> "Nürnberg". Brackets stay: "Frankfurt (Oder)" is its own city.
    nullif(trim(split_part(place ->> '$.adresse.ort', ',', 1)), '') as city,
    place ->> '$.adresse.ort' as city_raw,
    place ->> '$.adresse.plz' as postal_code,
    place ->> '$.adresse.region' as region,
    place ->> '$.adresse.land' as country,
    try_cast(place ->> '$.breite' as double) as latitude,
    try_cast(place ->> '$.laenge' as double) as longitude
from numbered
