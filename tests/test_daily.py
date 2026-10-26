import os

import pytest

from skillradar import daily
from skillradar.transform.runner import TransformError


def touch(path, mtime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
    os.utime(path, (mtime, mtime))


@pytest.fixture
def calls(monkeypatch):
    seen = {"snapshot": [], "build": [], "notify": []}

    def fake_snapshot(argv):
        seen["snapshot"].append(argv)
        return seen.get("snapshot_code", 0)

    def fake_build(data_dir):
        seen["build"].append(data_dir)
        if seen.get("build_error"):
            raise TransformError("dbt failed")

    monkeypatch.setattr(daily.snapshot_cli, "main", fake_snapshot)
    monkeypatch.setattr(daily, "build", fake_build)
    monkeypatch.setattr(daily, "notify", lambda title, message: seen["notify"].append(title))
    return seen


class TestNeedsTransform:
    def test_no_runs_yet(self, tmp_path):
        assert daily.needs_transform(tmp_path) is False

    def test_no_warehouse_yet(self, tmp_path):
        touch(tmp_path / "bronze/runs/run_1.json", 100)
        assert daily.needs_transform(tmp_path) is True

    def test_run_newer_than_warehouse(self, tmp_path):
        touch(tmp_path / "warehouse.duckdb", 100)
        touch(tmp_path / "bronze/runs/run_1.json", 200)
        assert daily.needs_transform(tmp_path) is True

    def test_warehouse_up_to_date(self, tmp_path):
        touch(tmp_path / "bronze/runs/run_1.json", 100)
        touch(tmp_path / "warehouse.duckdb", 200)
        assert daily.needs_transform(tmp_path) is False


def test_new_data_is_built(tmp_path, calls):
    touch(tmp_path / "bronze/runs/run_1.json", 100)

    assert daily.main(["--data-dir", str(tmp_path)]) == 0

    assert "--once-per-day" in calls["snapshot"][0] and "--notify" in calls["snapshot"][0]
    assert calls["build"] == [tmp_path.resolve()]


def test_nothing_new_nothing_built(tmp_path, calls):
    touch(tmp_path / "bronze/runs/run_1.json", 100)
    touch(tmp_path / "warehouse.duckdb", 200)

    assert daily.main(["--data-dir", str(tmp_path)]) == 0
    assert calls["build"] == []


def test_failed_snapshot_skips_build(tmp_path, calls):
    calls["snapshot_code"] = 1
    touch(tmp_path / "bronze/runs/run_1.json", 100)

    assert daily.main(["--data-dir", str(tmp_path)]) == 1
    assert calls["build"] == []


def test_failed_build_alerts_and_is_retried(tmp_path, calls):
    touch(tmp_path / "bronze/runs/run_1.json", 100)
    calls["build_error"] = True

    assert daily.main(["--data-dir", str(tmp_path)]) == 1
    assert calls["notify"] == ["SkillRadar transform failed"]

    # The warehouse was not updated, so the next hourly check builds again.
    calls["build_error"] = False
    assert daily.main(["--data-dir", str(tmp_path)]) == 0
    assert len(calls["build"]) == 2
