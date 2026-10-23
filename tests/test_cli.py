import pytest

from skillradar.ingestion import cli
from skillradar.ingestion.client import JobsucheError
from tests.helpers import FakeSource, posting


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
