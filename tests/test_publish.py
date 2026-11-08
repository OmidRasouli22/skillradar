import json
import os
import subprocess

import pytest

from skillradar.api.data import GoldData
from skillradar.publish import cli
from skillradar.publish.git import PublishError, push, remote_url
from skillradar.publish.site import export_data
from skillradar.skills.taxonomy import load_taxonomy
from skillradar.transform.runner import serve_dir
from tests.test_api import write_gold


def git(*args, cwd=None):
    result = subprocess.run(  # noqa: S603 - a test helper with fixed git commands
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def gold(tmp_path):
    write_gold(tmp_path)
    return GoldData(serve_dir(tmp_path), load_taxonomy())


@pytest.fixture
def page(tmp_path):
    folder = tmp_path / "page"
    (folder / "_next").mkdir(parents=True)
    (folder / "index.html").write_text("<h1>SkillRadar</h1>")
    (folder / "_next" / "app.js").write_text("console.log('page')")
    return folder


class TestExport:
    def test_files(self, gold, tmp_path):
        counts = export_data(gold, tmp_path / "site")
        data = tmp_path / "site" / "data"
        assert counts["jobs"] == 4 and counts["regions"] == 17
        assert json.loads((data / "overview.json").read_text())["tech_postings"] == 4
        assert (data / "dashboard" / "all.json").exists()
        assert (data / "dashboard" / "SAARLAND.json").exists()  # empty regions still answer
        listing = json.loads((data / "postings" / "data_engineer" / "all.json").read_text())
        assert listing["total"] == 2 and len(listing["items"]) == 2

    def test_lists_without_postings_are_left_out(self, gold, tmp_path):
        export_data(gold, tmp_path / "site")
        assert not (tmp_path / "site" / "data" / "postings" / "mobile_developer").exists()

    def test_jobs_have_no_text(self, gold, tmp_path):
        export_data(gold, tmp_path / "site")
        job = json.loads((tmp_path / "site" / "data" / "jobs" / "job-1.json").read_text())
        assert job["text"] == "" and job["marks"] == []
        assert job["skills"][0]["name"] == "SQL"
        everything = "".join(p.read_text() for p in (tmp_path / "site").rglob("*.json"))
        assert "Sehr gute SQL-Kenntnisse" not in everything


class TestPush:
    def test_push_replaces_the_branch(self, tmp_path):
        remote = tmp_path / "remote.git"
        git("init", "-q", "--bare", str(remote))
        for day in (1, 2):
            site = tmp_path / f"site{day}"
            site.mkdir()
            (site / "index.html").write_text(f"day {day}")
            push(site, str(remote), "gh-pages", f"Site data day {day}")
        assert git("log", "--format=%s", "gh-pages", cwd=remote) == "Site data day 2"
        assert git("show", "gh-pages:index.html", cwd=remote) == "day 2"

    def test_push_failure(self, tmp_path):
        site = tmp_path / "site"
        site.mkdir()
        (site / "index.html").write_text("x")
        with pytest.raises(PublishError, match="push"):
            push(site, str(tmp_path / "missing.git"), "gh-pages", "x")

    def test_unknown_remote(self, tmp_path):
        git("init", "-q", str(tmp_path))
        with pytest.raises(PublishError, match="no git remote"):
            remote_url(tmp_path, "nowhere")


class TestCli:
    def test_dry_run_builds_the_site(self, tmp_path, page, monkeypatch, capsys):
        write_gold(tmp_path)
        monkeypatch.setattr(cli, "PUBLIC_PAGE", page)
        assert cli.main(["--data-dir", str(tmp_path), "--dry-run"]) == 0
        site = tmp_path / "site"
        assert (site / "index.html").exists() and (site / "_next" / "app.js").exists()
        assert (site / ".nojekyll").exists() and (site / "data" / "overview.json").exists()
        health = json.loads((site / "data" / "health.json").read_text())
        assert health["freshness"]["state"] == "stale"  # no run logs in this test
        assert str(tmp_path) not in json.dumps(health)
        assert "not pushed" in capsys.readouterr().out

    def test_old_files_are_removed(self, tmp_path, page, monkeypatch):
        write_gold(tmp_path)
        monkeypatch.setattr(cli, "PUBLIC_PAGE", page)
        stale = tmp_path / "site" / "data" / "jobs" / "closed-job.json"
        stale.parent.mkdir(parents=True)
        stale.write_text("{}")
        cli.main(["--data-dir", str(tmp_path), "--dry-run"])
        assert not stale.exists()

    def test_page_not_built(self, tmp_path, monkeypatch, capsys):
        write_gold(tmp_path)
        monkeypatch.setattr(cli, "PUBLIC_PAGE", tmp_path / "nothing")
        assert cli.main(["--data-dir", str(tmp_path), "--dry-run"]) == 1
        assert "npm run build:public" in capsys.readouterr().err

    def test_no_data(self, tmp_path, page, monkeypatch, capsys):
        monkeypatch.setattr(cli, "PUBLIC_PAGE", page)
        assert cli.main(["--data-dir", str(tmp_path), "--dry-run"]) == 1
        assert "skillradar-transform" in capsys.readouterr().err

    def test_settings(self):
        settings = cli.load_site_settings()
        assert settings.branch == "gh-pages" and settings.remote == "origin"


class TestDailyPublish:
    def test_needs_publish(self, tmp_path):
        assert cli.needs_publish(tmp_path) is False  # no data yet
        write_gold(tmp_path)
        assert cli.needs_publish(tmp_path) is True  # never published
        cli.marker(tmp_path).touch()
        assert cli.needs_publish(tmp_path) is False
        newest = max(serve_dir(tmp_path).glob("*.parquet"))
        later = cli.marker(tmp_path).stat().st_mtime + 10
        os.utime(newest, (later, later))
        assert cli.needs_publish(tmp_path) is True  # new data after the last push

    def test_publishes_new_data_and_marks_it(self, tmp_path, monkeypatch):
        write_gold(tmp_path)
        pushed = []
        monkeypatch.setattr(cli, "publish", lambda data_dir, settings: pushed.append(data_dir))
        cli.daily_publish(tmp_path)
        cli.daily_publish(tmp_path)  # nothing new the second time
        assert pushed == [tmp_path] and cli.marker(tmp_path).exists()

    def test_switched_off(self, tmp_path, monkeypatch):
        write_gold(tmp_path)
        off = cli.load_site_settings().model_copy(update={"enabled": False})
        monkeypatch.setattr(cli, "load_site_settings", lambda: off)
        monkeypatch.setattr(cli, "publish", lambda *a: pytest.fail("must not publish"))
        cli.daily_publish(tmp_path)

    def test_failed_push_is_not_marked(self, tmp_path, monkeypatch):
        write_gold(tmp_path)

        def fail(data_dir, settings):
            raise PublishError("push failed")

        monkeypatch.setattr(cli, "publish", fail)
        with pytest.raises(PublishError):
            cli.daily_publish(tmp_path)
        assert not cli.marker(tmp_path).exists()  # so the next run tries again
