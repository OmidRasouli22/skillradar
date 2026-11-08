"""The weekly history tables, on two weeks of small test data.

Week of 2026-10-26 (two days): p1, p2 and p4 are open. p4 has no answer from Claude.
Week of 2026-11-02 (one day): p1, p3 and p5 are open, plus the apprenticeship p6.
p5 is not a tech job. p6 is not sent to Claude and not counted.
"""

import duckdb
import pytest

from skillradar.transform.runner import build, warehouse_path
from tests.helpers import write_jsonl, write_run_log
from tests.test_transform import details, llm_answer

BW = [{"adresse": {"ort": "Stuttgart", "region": "BADEN_WUERTTEMBERG"}}]
BY = [{"adresse": {"ort": "München", "region": "BAYERN"}}]

DAYS = {
    "20261026T060000Z": ["p1", "p2", "p4"],
    "20261027T060000Z": ["p1", "p2"],
    "20261102T060000Z": ["p1", "p3", "p5", "p6"],
}

POSTINGS = {
    "p1": details("p1", stellenangebotsBeschreibung="SQL und Python", stellenlokationen=BW),
    "p2": details("p2", stellenangebotsBeschreibung="SQL und Kafka", stellenlokationen=BY),
    "p3": details("p3", stellenangebotsBeschreibung="Python", stellenlokationen=BW),
    "p4": details("p4", stellenlokationen=BW),
    "p5": details("p5", stellenangebotsBeschreibung="Lager", stellenlokationen=BW),
    "p6": details("p6", stellenangebotsart="AUSBILDUNG", stellenlokationen=BW),
}

ANSWERS = [
    llm_answer(
        "p1", skills=[{"name": "SQL", "required": True}, {"name": "Python", "required": False}]
    ),
    llm_answer(
        "p2", skills=[{"name": "SQL", "required": True}, {"name": "Kafka", "required": True}]
    ),
    llm_answer("p3", role="backend_developer", skills=[{"name": "Python", "required": True}]),
    llm_answer("p5", role="not_tech", skills=[]),
]

WEEK_A, WEEK_B = "2026-10-26", "2026-11-02"


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    data = tmp_path_factory.mktemp("weekly")
    bronze = data / "bronze"
    for run, refnrs in DAYS.items():
        day = f"snapshot_date={run[:4]}-{run[4:6]}-{run[6:8]}"
        write_jsonl(
            bronze / "search" / day / f"run_{run}.jsonl.gz",
            [{"run_id": run, "posting": {"referenznummer": r}} for r in refnrs],
        )
        write_run_log(bronze, run, status="ok", full_scope=True)
    first_run = next(iter(DAYS))
    write_jsonl(
        bronze / "details" / "snapshot_date=2026-10-26" / f"run_{first_run}.jsonl",
        [{"run_id": first_run, "refnr": r, "details": d} for r, d in POSTINGS.items()],
    )
    write_jsonl(data / "llm/extractions/msgbatch_1.jsonl", ANSWERS)
    build(data)
    return data


def rows(data_dir, sql, params=()):
    with duckdb.connect(str(warehouse_path(data_dir))) as con:
        return con.execute(sql, params).fetchall()


def test_weeks(data_dir):
    result = rows(
        data_dir,
        "select strftime(week_start, '%Y-%m-%d'), strftime(week_end, '%Y-%m-%d'), "
        "snapshot_days, week_ended, open_postings, answered_postings, tech_postings, "
        "coverage from gold_weeks order by week_start",
    )
    assert result == [
        (WEEK_A, "2026-11-01", 2, True, 3, 2, 2, 0.6667),
        # Only its Monday has data, so the week is not over. p6 is not counted.
        (WEEK_B, "2026-11-08", 1, False, 3, 3, 2, 1.0),
    ]


def skills(data_dir, role, region):
    return rows(
        data_dir,
        "select strftime(week_start, '%Y-%m-%d'), skill, postings, required_postings, "
        "total_postings, share from gold_skill_weekly where role = ? and region = ? "
        "order by week_start, skill",
        (role, region),
    )


def test_all_postings_per_week(data_dir):
    assert skills(data_dir, "all", "all") == [
        (WEEK_A, "Kafka", 1, 1, 2, 0.5),
        (WEEK_A, "Python", 1, 0, 2, 0.5),
        (WEEK_A, "SQL", 2, 2, 2, 1.0),
        # Kafka's posting closed, so its series goes on with 0 instead of a gap.
        (WEEK_B, "Kafka", 0, 0, 2, 0.0),
        (WEEK_B, "Python", 2, 1, 2, 1.0),
        (WEEK_B, "SQL", 1, 1, 2, 0.5),
    ]


def test_role_and_region_groups(data_dir):
    assert skills(data_dir, "data_engineer", "BAYERN") == [
        (WEEK_A, "Kafka", 1, 1, 1, 1.0),
        (WEEK_A, "SQL", 1, 1, 1, 1.0),
        # No Data Engineer posting in Bavaria in week B: no rows, not rows with 0 of 0.
    ]
    assert skills(data_dir, "backend_developer", "all") == [(WEEK_B, "Python", 1, 1, 1, 1.0)]


def test_not_tech_and_apprenticeships_are_left_out(data_dir):
    [(refnrs,)] = rows(
        data_dir,
        "select max(total_postings) from gold_skill_weekly where week_start = ? "
        "and role = 'all' and region = 'BADEN_WUERTTEMBERG'",
        (WEEK_B,),
    )
    assert refnrs == 2  # p1 and p3, not p5 (not tech) or p6 (apprenticeship)
