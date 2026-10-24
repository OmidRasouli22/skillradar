"""Posting descriptions without personal data. The raw text stays in bronze only."""

import pyarrow as pa

from skillradar.clean.redact import redact


def model(dbt, session):
    dbt.config(materialized="table")
    rows = (
        dbt.ref("stg_details")
        .project("refnr, details ->> 'stellenangebotsBeschreibung' as description")
        .fetchall()
    )

    columns = {name: [] for name in ("refnr", "description", "emails", "phones", "links", "names")}
    for refnr, description in rows:
        result = redact(description or "")
        columns["refnr"].append(refnr)
        columns["description"].append(result.text)
        columns["emails"].append(result.emails)
        columns["phones"].append(result.phones)
        columns["links"].append(result.links)
        columns["names"].append(result.names)
    return pa.table(columns)
