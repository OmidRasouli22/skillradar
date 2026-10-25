"""History over five snapshot days.

Day 1 (Oct 20)  ok, full          sees: stays, closes, gap, comeback
Day 2 (Oct 21)  partial, full     sees: stays, closes
Day 3 (Oct 22)  ok, full          sees: stays
Day 4 (Oct 23)  no run log        sees: stays, comeback      (run was killed)
Day 5 (Oct 24)  ok, one city only sees: new                  (a test run)
"""

from datetime import date

import duckdb
import pytest

from skillradar.transform.runner import build, warehouse_path
from tests.helpers import write_jsonl, write_run_log

DAYS = {
    "20261020T050000Z": (
        ["stays", "closes", "gap", "comeback"],
        {"status": "ok", "full_scope": True},
    ),
    "20261021T050000Z": (["stays", "closes"], {"status": "partial", "full_scope": True}),
    "20261022T050000Z": (["stays"], {"status": "ok", "full_scope": True}),
    "20261023T050000Z": (["stays", "comeback"], None),
    "20261024T050000Z": (["new"], {"status": "ok", "full_scope": False}),
}


@pytest.fixture(scope="module")
def history(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    bronze = data / "bronze"
    for run_id, (refnrs, run_log) in DAYS.items():
        day = f"{run_id[:4]}-{run_id[4:6]}-{run_id[6:8]}"
        records = [
            {"run_id": run_id, "term": "Python", "city": "Berlin", "posting": {"referenznummer": r}}
            for r in refnrs
        ]
        # The same posting found by a second search must count once.
        records += [{**records[0], "term": "Java"}]
        write_jsonl(bronze / f"search/snapshot_date={day}/run_{run_id}.jsonl.gz", records)
        if run_log:
            write_run_log(bronze, run_id, **run_log)
    write_jsonl(bronze / "details/snapshot_date=2026-10-20/run_x.jsonl", [])

    build(data)
    with duckdb.connect(str(warehouse_path(data))) as con:
        rows = con.execute("select * from silver_posting_history").fetchall()
        columns = [c[0] for c in con.description]
        days = con.execute("select count(*) from silver_posting_days").fetchone()[0]
    return {row[0]: dict(zip(columns, row, strict=True)) for row in rows}, days


def oct(day):
    return date(2026, 10, day)


def test_posting_seen_every_day_is_open(history):
    stays = history[0]["stays"]
    assert (stays["first_seen"], stays["last_seen"], stays["days_seen"]) == (oct(20), oct(23), 4)
    assert stays["is_open"] and stays["closed_on"] is None


def test_closed_on_first_complete_day_without_it(history):
    closes = history[0]["closes"]
    assert closes["last_seen"] == oct(21)
    assert closes["closed_on"] == oct(22)
    assert not closes["is_open"]


def test_partial_day_does_not_close(history):
    # Missing on Oct 21, but that run was partial, so it closes on Oct 22.
    assert history[0]["gap"]["closed_on"] == oct(22)


def test_posting_that_comes_back_stays_open(history):
    comeback = history[0]["comeback"]
    assert comeback["days_seen"] == 2
    assert comeback["is_open"]


def test_test_run_does_not_close_anything(history):
    # Oct 24 was a one-city run. Postings missing from it stay open.
    assert history[0]["stays"]["is_open"]
    assert history[0]["new"]["first_seen"] == oct(24)


def test_one_row_per_posting_and_day(history):
    # stays 4 + closes 2 + gap 1 + comeback 2 + new 1, duplicates removed
    assert history[1] == 10
