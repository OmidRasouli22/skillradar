from datetime import UTC, datetime, timedelta, timezone

import pytest

from skillradar.ingestion.bronze import BronzeStore, RunKey
from tests.helpers import read_jsonl

RUN = RunKey(datetime(2026, 10, 23, 6, 0, 5, tzinfo=UTC))
NEXT_DAY = RunKey(datetime(2026, 10, 24, 6, 0, 0, tzinfo=UTC))


@pytest.fixture
def store(tmp_path):
    return BronzeStore(tmp_path / "bronze")


def mode(path):
    return path.stat().st_mode & 0o777


class TestRunKey:
    def test_names(self):
        assert RUN.run_id == "20261023T060005Z"
        assert RUN.snapshot_date == "2026-10-23"

    def test_rejects_time_without_zone(self):
        with pytest.raises(ValueError, match="UTC"):
            RunKey(datetime(2026, 10, 23, 6, 0))

    def test_rejects_other_zones(self):
        berlin = timezone(timedelta(hours=2))
        with pytest.raises(ValueError, match="UTC"):
            RunKey(datetime(2026, 10, 23, 8, 0, tzinfo=berlin))


class TestSearch:
    def test_writes_one_line_per_record(self, store):
        records = [{"refnr": "a", "city": "München"}, {"refnr": "b", "city": "Köln"}]

        path = store.write_search(RUN, records)

        assert path == store.root / "search/snapshot_date=2026-10-23/run_20261023T060005Z.jsonl"
        assert read_jsonl(path) == records
        assert "München" in path.read_text(encoding="utf-8")

    def test_files_and_folders_are_private(self, store):
        path = store.write_search(RUN, [{"refnr": "a"}])

        assert mode(path) == 0o600
        assert mode(path.parent) == 0o700

    def test_leaves_no_temp_files(self, store):
        path = store.write_search(RUN, [{"refnr": "a"}])

        assert [p.name for p in path.parent.iterdir()] == [path.name]

    def test_failed_write_keeps_old_file(self, store):
        path = store.write_search(RUN, [{"refnr": "old"}])

        def broken_records():
            yield {"refnr": "new"}
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            store.write_search(RUN, broken_records())

        assert read_jsonl(path) == [{"refnr": "old"}]
        assert [p.name for p in path.parent.iterdir()] == [path.name]


class TestDetails:
    def test_writer_saves_records(self, store):
        with store.details_writer(RUN) as write:
            write({"refnr": "a", "details": {"x": 1}})
            write({"refnr": "b", "details": None})

        path = store.root / "details/snapshot_date=2026-10-23/run_20261023T060005Z.jsonl"
        assert read_jsonl(path) == [
            {"refnr": "a", "details": {"x": 1}},
            {"refnr": "b", "details": None},
        ]
        assert mode(path) == 0o600

    def test_writer_keeps_work_when_run_fails(self, store):
        with pytest.raises(RuntimeError):
            with store.details_writer(RUN) as write:
                write({"refnr": "a", "details": {}})
                raise RuntimeError("boom")

        assert store.known_refnrs() == {"a"}
        assert not list(store.root.rglob("*.part"))


class TestKnownRefnrs:
    def test_empty_store(self, store):
        assert store.known_refnrs() == set()

    def test_collects_refnrs_over_days(self, store):
        with store.details_writer(RUN) as write:
            write({"refnr": "a"})
        with store.details_writer(NEXT_DAY) as write:
            write({"refnr": "b"})

        assert store.known_refnrs() == {"a", "b"}

    def test_skips_broken_lines_and_part_files(self, store):
        folder = store.root / "details/snapshot_date=2026-10-23"
        folder.mkdir(parents=True)
        (folder / "run_1.jsonl").write_text('{"refnr": "a"}\nnot json\n[1, 2]\n{"refnr": 5}\n')
        (folder / "run_2.jsonl.part").write_text('{"refnr": "unfinished"}\n')

        assert store.known_refnrs() == {"a"}


def test_run_log(store):
    path = store.write_run_log(RUN, {"status": "ok", "errors": []})

    assert path.name == "run_20261023T060005Z.json"
    assert '"status": "ok"' in path.read_text()
    assert mode(path) == 0o600
