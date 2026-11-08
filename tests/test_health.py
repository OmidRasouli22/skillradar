import json
from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from skillradar.extract.prompt import PROMPT_VERSION
from skillradar.extract.settings import load_settings
from skillradar.health import build_health, freshness
from skillradar.storage import json_line
from skillradar.transform.runner import serve_dir
from tests.helpers import write_run_log

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
MODEL = load_settings().model
USAGE = {"input_tokens": 1000, "output_tokens": 1000}  # $0.0003 each at Haiku batch price


def answer(refnr, batch_id, status="ok"):
    return {
        "refnr": refnr,
        "batch_id": batch_id,
        "model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "extracted_at": "2026-11-06T10:00:00+00:00",
        "status": status,
        "output": {},
        "usage": USAGE,
    }


@pytest.fixture
def data_dir(tmp_path):
    bronze = tmp_path / "bronze"
    write_run_log(bronze, "20261105T080000Z", status="ok", full_scope=True,
                  started_at="2026-11-05T08:00:00+00:00",
                  finished_at="2026-11-05T08:10:00+00:00", new_postings=120)  # fmt: skip
    write_run_log(bronze, "20261106T080000Z", status="failed",
                  started_at="2026-11-06T08:00:00+00:00",
                  errors=["network error for /pc/v6/jobs: secret detail"])  # fmt: skip
    write_run_log(bronze, "20261107T080000Z", status="partial", full_scope=True,
                  started_at="2026-11-07T08:00:00+00:00",
                  finished_at="2026-11-07T08:09:30+00:00", new_postings=183,
                  errors=["one search failed"])  # fmt: skip

    target = tmp_path / "dbt" / "target"
    target.mkdir(parents=True)
    (target / "run_results.json").write_text(
        json.dumps(
            {
                "metadata": {"generated_at": "2026-11-07T08:12:00Z"},
                "elapsed_time": 26.43,
                "results": [
                    {"unique_id": "model.skillradar.silver_postings", "status": "success"},
                    {"unique_id": "test.skillradar.unique_x.abc", "status": "pass"},
                    {"unique_id": "test.skillradar.gold_counts_add_up", "status": "fail"},
                ],
            }
        )
    )

    llm = tmp_path / "llm"
    (llm / "batches" / "done").mkdir(parents=True)
    (llm / "batches" / "pending").mkdir(parents=True)
    (llm / "extractions").mkdir(parents=True)
    done = {"batch_id": "msgbatch_done", "created_at": "2026-11-06T09:00:00+00:00", "model": MODEL,
            "prompt_version": PROMPT_VERSION, "refnrs": {"a": "r1", "b": "r2", "c": "r3"},
            "max_cost_usd": 0.01}  # fmt: skip
    (llm / "batches" / "done" / "msgbatch_done.json").write_text(json.dumps(done))
    pending = {**done, "batch_id": "msgbatch_wait", "refnrs": {"d": "r4"}, "max_cost_usd": 0.05}
    (llm / "batches" / "pending" / "msgbatch_wait.json").write_text(json.dumps(pending))
    (llm / "extractions" / "msgbatch_done.jsonl").write_text(
        "".join(
            json_line(answer(r, "msgbatch_done", s))
            for r, s in [("r1", "ok"), ("r2", "ok"), ("r3", "error")]
        )  # fmt: skip
    )

    serve = serve_dir(tmp_path)
    serve.mkdir()
    with duckdb.connect() as con:
        con.execute(
            "copy (select date '2026-11-07' as as_of, 100 as open_postings, "
            "96 as postings_with_answers, 80 as tech_postings) "
            f"to '{serve / 'gold_meta.parquet'}' (format parquet)"
        )
    return tmp_path


@pytest.fixture
def health(data_dir):
    return build_health(data_dir, NOW)


def test_runs_newest_first_without_error_texts(health):
    runs = health["runs"]
    ids = [r["run_id"] for r in runs]
    assert ids == ["20261107T080000Z", "20261106T080000Z", "20261105T080000Z"]
    assert runs[0]["minutes"] == 9.5 and runs[0]["errors"] == 1 and runs[0]["new_postings"] == 183
    assert runs[1]["minutes"] is None  # a failed run without an end time


def test_freshness_uses_the_last_run_that_saved_data(health):
    # The failed run doesn't count; the partial one from 08:00 is 4 hours old.
    assert health["freshness"] == {
        "last_success": "2026-11-07T08:00:00+00:00",
        "hours": 4.0,
        "state": "fresh",
    }


@pytest.mark.parametrize("hours, state", [(29, "fresh"), (31, "late"), (53, "late"), (55, "stale")])
def test_freshness_states(hours, state):
    runs = [{"status": "ok", "started_at": (NOW - timedelta(hours=hours)).isoformat()}]
    assert freshness(runs, NOW)["state"] == state


def test_no_good_run_is_stale():
    assert freshness([{"status": "failed", "started_at": NOW.isoformat()}], NOW)["state"] == "stale"


def test_dbt_results(health):
    tests = health["tests"]
    assert tests["models"] == {"success": 1} and tests["tests"] == {"pass": 1, "fail": 1}
    assert tests["failures"] == [{"name": "gold_counts_add_up", "status": "fail"}]
    assert tests["seconds"] == 26.4


def test_claude(health):
    claude = health["claude"]
    assert claude["model"] == MODEL and claude["prompt_version"] == PROMPT_VERSION
    assert (claude["answers"], claude["failed_answers"]) == (2, 1)
    assert (claude["pending_batches"], claude["pending_postings"]) == (1, 1)
    [batch] = claude["batches"]
    assert (batch["postings"], batch["answers"], batch["failed"]) == (3, 2, 1)
    assert batch["cost_usd"] == pytest.approx(0.0009)
    # Answers saved this month plus the pending batch at its worst case.
    assert claude["spent_usd"] == pytest.approx(round(0.0009 + 0.05, 2))


def test_coverage(health):
    coverage = health["coverage"]
    assert (coverage["open_postings"], coverage["with_answer"]) == (100, 96)
    assert coverage["share"] == 0.96


def test_only_the_shown_parts_are_published(health):
    parts = {"generated_at", "thresholds", "freshness", "runs", "tests", "claude", "coverage"}
    assert set(health) == parts


def test_nothing_private_is_published(data_dir, health):
    text = json.dumps(health)
    assert str(data_dir) not in text
    assert "secret detail" not in text and "one search failed" not in text
    assert "msgbatch" not in text


def test_empty_data_folder(tmp_path):
    health = build_health(tmp_path, NOW)
    assert health["runs"] == [] and health["freshness"]["state"] == "stale"
    assert health["tests"] is None and health["coverage"] is None
    assert health["claude"]["answers"] == 0


def test_a_failing_part_leaves_the_rest(data_dir, caplog):
    # A gold_meta from an older build, without the columns this page reads.
    with duckdb.connect() as con:
        con.execute(f"copy (select 1 as x) to '{serve_dir(data_dir) / 'gold_meta.parquet'}'")
    health = build_health(data_dir, NOW)
    assert health["coverage"] is None and len(health["runs"]) == 3
    assert "coverage part failed" in caplog.text


def test_broken_files_are_skipped(data_dir):
    (data_dir / "dbt" / "target" / "run_results.json").write_text("{not json")
    (data_dir / "bronze" / "runs" / "run_20261108T080000Z.json").write_text("[]")
    health = build_health(data_dir, NOW)
    assert health["tests"] is None and len(health["runs"]) == 3
