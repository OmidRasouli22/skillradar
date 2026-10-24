-- One clean row per posting.

with details as (
    select * from {{ ref('stg_details') }}
)

select
    refnr,
    details ->> 'stellenangebotsTitel' as title,
    details ->> 'firma' as employer,
    details ->> 'arbeitgeberKundennummerHash' as employer_id,
    details ->> 'stellenangebotsart' as posting_type,
    details ->> 'hauptberuf' as occupation,
    try_cast(details ->> 'arbeitszeitVollzeit' as boolean) as full_time,
    details ->> 'vertragsdauer' as contract,
    try_cast(details ->> 'homeofficemoeglich' as boolean) as home_office,
    try_cast(details ->> 'homeofficeprozent' as integer) as home_office_percent,
    details ->> 'verguetungsangabe' as pay_type,
    coalesce(
        try_cast(details ->> 'gehaltsspanneVon' as double),
        try_cast(details ->> 'festgehalt' as double)
    ) as salary_min,
    coalesce(
        try_cast(details ->> 'gehaltsspanneBis' as double),
        try_cast(details ->> 'festgehalt' as double)
    ) as salary_max,
    try_cast(details ->> 'istArbeitnehmerUeberlassung' as boolean) as is_staffing_agency,
    try_cast(details ->> 'istPrivateArbeitsvermittlung' as boolean) as is_private_recruiter,
    try_cast(details ->> 'datumErsteVeroeffentlichung' as date) as first_published,
    try_cast(details ->> 'aenderungsdatum' as timestamp) as changed_at,
    details ->> 'stellenangebotsBeschreibung' as description,
    length(details ->> 'stellenangebotsBeschreibung') as description_chars,
    run_id as details_run_id
from details
