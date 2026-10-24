import json

import pytest

from skillradar.config import load_config
from skillradar.ingestion.bronze import BronzeStore
from skillradar.ingestion.client import JobsucheError
from skillradar.ingestion.snapshot import run_snapshot
from tests.helpers import FakeClock, FakeSource, posting, read_jsonl

STUTTGART_DE = ("Data Engineer", "Stuttgart")
STUTTGART_PY = ("Python", "Stuttgart")
BERLIN_DE = ("Data Engineer", "Berlin")
BERLIN_PY = ("Python", "Berlin")


@pytest.fixture
def config():
    return load_config().only(cities=["Stuttgart", "Berlin"], terms=["Data Engineer", "Python"])


@pytest.fixture
def store(tmp_path):
    return BronzeStore(tmp_path / "bronze")


@pytest.fixture
def clock():
    return FakeClock()


def run(config, source, store, clock):
    return run_snapshot(config, source, store, clock=clock)


def only_file(store, kind):
    [path] = [p for p in store.root.glob(f"{kind}/**/*") if p.is_file()]
    return path


def test_happy_path(config, store, clock):
    source = FakeSource({STUTTGART_DE: [posting("a"), posting("b")], BERLIN_PY: [posting("c")]})

    summary = run(config, source, store, clock)

    assert summary.status == "ok"
    assert summary.queries == 4
    assert summary.unique_postings == 3
    assert summary.details_saved == 3
    assert summary.errors == []

    search = read_jsonl(only_file(store, "search"))
    assert {r["posting"]["referenznummer"] for r in search} == {"a", "b", "c"}
    assert search[0]["term"] == "Data Engineer" and search[0]["city"] == "Stuttgart"

    run_log = json.loads(only_file(store, "runs").read_text())
    assert run_log["status"] == "ok"
    assert run_log["finished_at"] > run_log["started_at"]


def test_same_posting_from_two_searches_is_fetched_once(config, store, clock):
    source = FakeSource({STUTTGART_DE: [posting("a")], STUTTGART_PY: [posting("a")]})

    summary = run(config, source, store, clock)

    assert summary.postings_seen == 2
    assert summary.unique_postings == 1
    assert source.details_calls == ["a"]
    assert len(read_jsonl(only_file(store, "search"))) == 2


def test_second_run_fetches_only_new_postings(config, store, clock):
    run(config, FakeSource({STUTTGART_DE: [posting("a"), posting("b")]}), store, clock)
    source = FakeSource({STUTTGART_DE: [posting("a"), posting("b"), posting("c")]})

    summary = run(config, source, store, clock)

    assert source.details_calls == ["c"]
    assert summary.new_postings == 1


def test_gone_posting_is_saved_and_not_fetched_again(config, store, clock):
    run(config, FakeSource({BERLIN_DE: [posting("a")]}, details={"a": None}), store, clock)
    source = FakeSource({BERLIN_DE: [posting("a")]})

    summary = run(config, source, store, clock)

    assert source.details_calls == []
    assert summary.new_postings == 0


def test_failed_search_does_not_stop_the_run(config, store, clock):
    source = FakeSource({STUTTGART_DE: JobsucheError("500"), BERLIN_DE: [posting("a")]})

    summary = run(config, source, store, clock)

    assert summary.status == "partial"
    assert summary.failed_queries == 1
    assert "Stuttgart" in summary.errors[0]
    assert source.details_calls == ["a"]


def test_all_searches_failing_marks_run_failed(config, store, clock):
    error = JobsucheError("403")
    source = FakeSource({q: error for q in (STUTTGART_DE, STUTTGART_PY, BERLIN_DE, BERLIN_PY)})

    summary = run(config, source, store, clock)

    assert summary.status == "failed"
    assert not list(store.root.glob("search/*/*"))
    assert source.details_calls == []


def test_failed_details_are_retried_next_run(config, store, clock):
    searches = {BERLIN_DE: [posting("a"), posting("b")]}
    source = FakeSource(searches, details={"a": JobsucheError("x")})

    summary = run(config, source, store, clock)

    assert summary.status == "partial"
    assert summary.failed_details == 1
    assert store.known_refnrs() == {"b"}

    retry = FakeSource(searches)
    run(config, retry, store, clock)
    assert retry.details_calls == ["a"]


@pytest.mark.parametrize("bad_refnr", [None, 123, "", "../../etc/passwd", "a/b", "x" * 65])
def test_unsafe_refnrs_are_skipped(config, store, clock, bad_refnr):
    source = FakeSource({BERLIN_DE: [posting(bad_refnr), posting("ok"), {"no": "refnr"}]})

    summary = run(config, source, store, clock)

    assert summary.invalid_postings == 2
    assert source.details_calls == ["ok"]
    assert len(read_jsonl(only_file(store, "search"))) == 1


def test_crash_still_writes_run_log(config, store, clock):
    source = FakeSource({STUTTGART_DE: [posting("a")]}, details={"a": RuntimeError("bug")})

    with pytest.raises(RuntimeError):
        run(config, source, store, clock)

    run_log = json.loads(only_file(store, "runs").read_text())
    assert run_log["status"] == "failed"
    assert "bug" in run_log["errors"][-1]
    assert store.known_refnrs() == set()


def test_details_from_killed_run_are_not_fetched_again(config, store, clock):
    folder = store.root / "details/snapshot_date=2026-10-22"
    folder.mkdir(parents=True)
    (folder / "run_20261022T060000Z.jsonl.part").write_text('{"refnr": "a", "details": {}}\n')
    source = FakeSource({BERLIN_DE: [posting("a"), posting("b")]})

    summary = run(config, source, store, clock)

    assert summary.recovered_files == 1
    assert source.details_calls == ["b"]


@pytest.mark.parametrize("stop", [KeyboardInterrupt(), SystemExit("stopped by signal 15")])
def test_stopped_run_keeps_details_and_writes_log(config, store, clock, stop):
    searches = {BERLIN_DE: [posting("a"), posting("b")]}
    source = FakeSource(searches, details={"b": stop})

    with pytest.raises(type(stop)):
        run(config, source, store, clock)

    run_log = json.loads(only_file(store, "runs").read_text())
    assert run_log["status"] == "failed"
    assert store.known_refnrs() == {"a"}
    assert not list(store.root.rglob("*.part"))


def test_progress_is_logged(config, store, clock, caplog, monkeypatch):
    monkeypatch.setattr("skillradar.ingestion.snapshot.PROGRESS_EVERY", 2)
    source = FakeSource({BERLIN_DE: [posting(str(i)) for i in range(5)]})

    with caplog.at_level("INFO"):
        run(config, source, store, clock)

    assert "fetching details for 5 new postings" in caplog.text
    assert "details 2/5" in caplog.text and "details 4/5" in caplog.text


@pytest.mark.parametrize("full_scope", [True, False])
def test_run_log_records_scope(config, store, clock, full_scope):
    run_snapshot(config, FakeSource(), store, clock=clock, full_scope=full_scope)

    assert json.loads(only_file(store, "runs").read_text())["full_scope"] is full_scope
