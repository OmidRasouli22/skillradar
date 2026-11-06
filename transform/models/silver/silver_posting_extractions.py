"""Role, seniority and remote per posting, from Claude's answers to the current prompt."""

import os
from pathlib import Path

import pyarrow as pa

from skillradar.extract.tables import load_current_answers, posting_rows

SCHEMA = pa.schema(
    [
        ("refnr", pa.string()),
        ("role", pa.string()),
        ("seniority", pa.string()),
        ("remote", pa.string()),
        ("model", pa.string()),
        ("prompt_version", pa.string()),
        ("extracted_at", pa.string()),
    ]
)


def model(dbt, session):
    dbt.config(materialized="table")
    refnrs = {row[0] for row in dbt.ref("silver_postings").project("refnr").fetchall()}
    answers = load_current_answers(Path(os.environ["SKILLRADAR_LLM_DIR"]), refnrs)
    return pa.Table.from_pylist(posting_rows(answers), schema=SCHEMA)
