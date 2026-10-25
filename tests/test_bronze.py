import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from skillradar.ingestion.bronze import BronzeStore, RunKey
from tests.helpers import read_jsonl, read_text, write_run_log

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

        assert path == store.root / "search/snapshot_date=2026-10-23/run_20261023T060005Z.jsonl.gz"
        assert read_jsonl(path) == records
        assert "München" in read_text(path)

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


class TestRecover:
    def test_nothing_to_recover(self, store):
        assert store.recover_unfinished() == 0

    def test_killed_run_is_kept(self, store):
        folder = store.root / "details/snapshot_date=2026-10-23"
        folder.mkdir(parents=True)
        # The last line was cut off when the process was killed.
        (folder / "run_1.jsonl.part").write_text('{"refnr": "a"}\n{"refnr": "b"}\n{"refnr": "c')

        assert store.recover_unfinished() == 1
        assert [p.name for p in folder.iterdir()] == ["run_1.jsonl"]
        assert store.known_refnrs() == {"a", "b"}


class TestCompress:
    def test_old_plain_files_are_compressed(self, store):
        folder = store.root / "search/snapshot_date=2026-10-23"
        folder.mkdir(parents=True)
        (folder / "run_1.jsonl").write_text('{"refnr": "a", "city": "München"}\n')

        assert store.compress_search_files() == 1
        [path] = folder.iterdir()
        assert path.name == "run_1.jsonl.gz"
        assert read_jsonl(path) == [{"refnr": "a", "city": "München"}]
        assert mode(path) == 0o600

    def test_nothing_to_compress(self, store):
        store.write_search(RUN, [{"refnr": "a"}])

        assert store.compress_search_files() == 0

    def test_compressed_file_is_much_smaller(self, store):
        records = [
            {"refnr": str(i), "posting": {"titel": "Data Engineer (m/w/d)"}} for i in range(500)
        ]
        path = store.write_search(RUN, records)

        plain = sum(len(json.dumps(r)) + 1 for r in records)
        assert path.stat().st_size < plain / 5


class TestFinishedRun:
    @pytest.mark.parametrize(
        "log, expected",
        [
            ({"status": "ok", "full_scope": True}, True),
            ({"status": "partial", "full_scope": True}, True),
            ({"status": "failed", "full_scope": True}, False),
            ({"status": "ok", "full_scope": False}, False),
            ({"status": "ok"}, False),
        ],
    )
    def test_status_and_scope(self, store, log, expected):
        write_run_log(store.root, "20261023T060000Z", **log)

        assert store.has_finished_run("2026-10-23") is expected

    def test_other_days_do_not_count(self, store):
        write_run_log(store.root, "20261022T060000Z", status="ok", full_scope=True)

        assert store.has_finished_run("2026-10-23") is False

    def test_broken_log_is_ignored(self, store):
        (store.root / "runs").mkdir(parents=True)
        (store.root / "runs/run_20261023T060000Z.json").write_text("{not json")

        assert store.has_finished_run("2026-10-23") is False
