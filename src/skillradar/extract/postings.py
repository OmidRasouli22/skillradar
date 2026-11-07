"""Postings to send to Claude, read from the silver tables."""

from pathlib import Path

import duckdb

from skillradar.extract.batch import PostingText

# Apprenticeships are left out: they ask for school grades, not skills.
POSTINGS_SQL = """
    select t.refnr, coalesce(p.title, ''), t.description
    from silver_posting_texts t
    join silver_postings p using (refnr)
    where p.posting_type is distinct from 'AUSBILDUNG' {only_open}
    order by p.first_published desc nulls last, t.refnr
"""
ONLY_OPEN = "and t.refnr in (select refnr from silver_posting_history where is_open)"


def load_postings(warehouse: Path, only_open: bool = False) -> list[PostingText]:
    sql = POSTINGS_SQL.format(only_open=ONLY_OPEN if only_open else "")
    # Not read_only: the daily job calls this right after dbt, whose connection is still
    # open in this process, and DuckDB refuses a second one with other settings.
    with duckdb.connect(str(warehouse)) as con:
        return [PostingText(*row) for row in con.execute(sql).fetchall()]
