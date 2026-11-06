"""Human languages each posting asks for, with the level. From the current prompt."""

import os
from pathlib import Path

import pyarrow as pa

from skillradar.extract.tables import language_rows, load_current_answers

SCHEMA = pa.schema([("refnr", pa.string()), ("language", pa.string()), ("level", pa.string())])


def model(dbt, session):
    dbt.config(materialized="table")
    refnrs = {row[0] for row in dbt.ref("silver_postings").project("refnr").fetchall()}
    answers = load_current_answers(Path(os.environ["SKILLRADAR_LLM_DIR"]), refnrs)
    return pa.Table.from_pylist(language_rows(answers), schema=SCHEMA)
