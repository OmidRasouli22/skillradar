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
    seen = {"snapshot": [], "build": [], "notify": [], "order": []}

    def fake_snapshot(argv):
        seen["snapshot"].append(argv)
        return seen.get("snapshot_code", 0)

    def fake_build(data_dir):
        seen["build"].append(data_dir)
        seen["order"].append("build")
        if seen.get("build_error"):
            raise TransformError("dbt failed")
        (data_dir / "warehouse.duckdb").write_text("built")  # a real build updates it

    def fake_step(name):
        def step(data_dir):
            seen["order"].append(name)
            if seen.get("claude_error"):
                raise RuntimeError("bug in a Claude step")
            if name == "wait" and seen.get("new_answers"):
                touch(data_dir / "llm/extractions/msgbatch_1.jsonl", 4_000_000_000)

        step.__name__ = name
        return step

    monkeypatch.setattr(daily.snapshot_cli, "main", fake_snapshot)
    monkeypatch.setattr(daily, "build", fake_build)
    monkeypatch.setattr(daily.auto, "collect_step", fake_step("collect"))
    monkeypatch.setattr(daily.auto, "submit_step", fake_step("submit"))
    monkeypatch.setattr(daily.auto, "wait_step", fake_step("wait"))
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

    def test_new_answers_from_claude(self, tmp_path):
        touch(tmp_path / "bronze/runs/run_1.json", 100)
        touch(tmp_path / "warehouse.duckdb", 200)
        touch(tmp_path / "llm/extractions/msgbatch_1.jsonl", 300)
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

    # The warehouse was not updated, so the next run builds again.
    calls["build_error"] = False
    assert daily.main(["--data-dir", str(tmp_path)]) == 0
    assert len(calls["build"]) == 2


def test_claude_steps_run_around_the_build(tmp_path, calls):
    touch(tmp_path / "bronze/runs/run_1.json", 100)

    assert daily.main(["--data-dir", str(tmp_path)]) == 0
    # Old answers are collected before the build, new postings are sent after it.
    assert calls["order"] == ["collect", "build", "submit", "wait"]


def test_new_answers_are_built_the_same_day(tmp_path, calls):
    touch(tmp_path / "bronze/runs/run_1.json", 100)
    calls["new_answers"] = True

    assert daily.main(["--data-dir", str(tmp_path)]) == 0
    assert calls["order"] == ["collect", "build", "submit", "wait", "build"]


def test_claude_steps_run_when_nothing_is_new(tmp_path, calls):
    touch(tmp_path / "bronze/runs/run_1.json", 100)
    touch(tmp_path / "warehouse.duckdb", 200)

    assert daily.main(["--data-dir", str(tmp_path)]) == 0
    assert calls["order"] == ["collect", "submit", "wait"]


def test_failed_snapshot_skips_claude(tmp_path, calls):
    calls["snapshot_code"] = 1
    assert daily.main(["--data-dir", str(tmp_path)]) == 1
    assert calls["order"] == []


def test_failed_build_skips_submit(tmp_path, calls):
    touch(tmp_path / "bronze/runs/run_1.json", 100)
    calls["build_error"] = True

    assert daily.main(["--data-dir", str(tmp_path)]) == 1
    assert calls["order"] == ["collect", "build"]


def test_bug_in_a_claude_step_does_not_stop_the_job(tmp_path, calls, capsys):
    touch(tmp_path / "bronze/runs/run_1.json", 100)
    calls["claude_error"] = True

    assert daily.main(["--data-dir", str(tmp_path)]) == 0
    assert calls["order"] == ["collect", "build", "submit", "wait"]
    assert "claude step collect failed" in capsys.readouterr().out
