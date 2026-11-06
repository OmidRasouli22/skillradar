"""Skills per posting from the current prompt, checked against the posting text."""

import os
from pathlib import Path

import pyarrow as pa

from skillradar.extract.tables import load_current_answers, skill_rows
from skillradar.skills.taxonomy import load_taxonomy

SCHEMA = pa.schema(
    [
        ("refnr", pa.string()),
        ("skill", pa.string()),
        ("category", pa.string()),
        ("general", pa.bool_()),
        ("emerging", pa.bool_()),
        ("required", pa.bool_()),
        ("in_skill_list", pa.bool_()),
        ("in_text", pa.bool_()),
    ]
)


def model(dbt, session):
    dbt.config(materialized="table")
    titles = dict(dbt.ref("silver_postings").project("refnr, title").fetchall())
    descriptions = dbt.ref("silver_posting_texts").project("refnr, description").fetchall()
    texts = {refnr: f"{titles.get(refnr) or ''}\n{text}" for refnr, text in descriptions}
    answers = load_current_answers(Path(os.environ["SKILLRADAR_LLM_DIR"]), set(titles))
    return pa.Table.from_pylist(skill_rows(answers, load_taxonomy(), texts), schema=SCHEMA)
