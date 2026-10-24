import json
import signal

import pytest

from skillradar.config import load_config
from skillradar.ingestion import cli
from skillradar.ingestion.client import JobsucheError
from skillradar.lock import run_lock
from tests.helpers import FakeSource, posting


@pytest.fixture(autouse=True)
def restore_sigterm():
    original = signal.getsignal(signal.SIGTERM)
    yield
    signal.signal(signal.SIGTERM, original)


@pytest.fixture
def use_source(monkeypatch):
    def install(source):
        monkeypatch.setattr(cli, "JobsucheClient", lambda api_config: source)

    return install


def test_run_writes_bronze(tmp_path, use_source):
    use_source(FakeSource({("Python", "Berlin"): [posting("a")]}))

    code = cli.main(["--data-dir", str(tmp_path), "--city", "Berlin", "--term", "Python"])

    assert code == 0
    assert list(tmp_path.glob("bronze/search/*/*.jsonl"))
    assert list(tmp_path.glob("bronze/details/*/*.jsonl"))
    assert list(tmp_path.glob("bronze/runs/*.json"))


def test_failed_run_returns_error_code(tmp_path, use_source):
    use_source(FakeSource({("Python", "Berlin"): JobsucheError("403")}))

    code = cli.main(["--data-dir", str(tmp_path), "--city", "Berlin", "--term", "Python"])

    assert code == 1


def test_unknown_city_is_rejected(tmp_path, use_source):
    use_source(FakeSource())

    code = cli.main(["--data-dir", str(tmp_path), "--city", "Atlantis"])

    assert code == 2
    assert not tmp_path.joinpath("bronze").exists()


@pytest.fixture
def alerts(monkeypatch):
    sent = []
    monkeypatch.setattr(cli, "notify", lambda title, message: sent.append(title))
    return sent


def test_notify_on_failed_run(tmp_path, use_source, alerts):
    use_source(FakeSource({("Python", "Berlin"): JobsucheError("403")}))

    cli.main(["--data-dir", str(tmp_path), "--city", "Berlin", "--term", "Python", "--notify"])

    assert alerts == ["SkillRadar run failed"]


def test_no_alert_when_run_is_ok(tmp_path, use_source, alerts):
    use_source(FakeSource({("Python", "Berlin"): [posting("a")]}))

    cli.main(["--data-dir", str(tmp_path), "--city", "Berlin", "--term", "Python", "--notify"])

    assert alerts == []


def test_no_alert_without_flag(tmp_path, use_source, alerts):
    use_source(FakeSource({("Python", "Berlin"): JobsucheError("403")}))

    cli.main(["--data-dir", str(tmp_path), "--city", "Berlin", "--term", "Python"])

    assert alerts == []


def test_alert_on_crash(tmp_path, use_source, alerts):
    use_source(FakeSource({("Python", "Berlin"): [posting("a")]}, details={"a": RuntimeError()}))

    with pytest.raises(RuntimeError):
        cli.main(["--data-dir", str(tmp_path), "--city", "Berlin", "--term", "Python", "--notify"])

    assert alerts == ["SkillRadar run crashed"]


def test_second_run_at_the_same_time_is_refused(tmp_path, use_source):
    use_source(FakeSource())

    with run_lock(tmp_path / ".snapshot.lock"):
        code = cli.main(["--data-dir", str(tmp_path), "--city", "Berlin", "--term", "Python"])

    assert code == 3
    assert not tmp_path.joinpath("bronze").exists()


def test_sigterm_becomes_an_exception():
    cli.stop_on_sigterm()
    handler = signal.getsignal(signal.SIGTERM)

    with pytest.raises(SystemExit, match="signal 15"):
        handler(signal.SIGTERM, None)


@pytest.mark.parametrize(
    "extra, full_scope", [([], True), (["--city", "Berlin"], False), (["--term", "Java"], False)]
)
def test_filtered_runs_are_marked(tmp_path, use_source, monkeypatch, extra, full_scope):
    monkeypatch.setattr(cli, "load_config", lambda path: load_config().only(["Berlin"], ["Java"]))
    use_source(FakeSource())

    cli.main(["--data-dir", str(tmp_path), *extra])

    [log] = tmp_path.glob("bronze/runs/*.json")
    assert json.loads(log.read_text())["full_scope"] is full_scope
