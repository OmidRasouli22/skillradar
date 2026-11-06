import logging

import anthropic
import duckdb
import httpx2
import pytest

from skillradar.extract import auto
from skillradar.extract.batch import custom_id
from skillradar.extract.settings import load_settings
from skillradar.extract.store import ExtractionStore
from tests.test_extract import FakeClient, succeeded


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """A warehouse with one open, one closed and one apprenticeship posting."""
    with duckdb.connect(str(tmp_path / "warehouse.duckdb")) as con:
        con.execute(
            "create table silver_postings (refnr varchar, title varchar, "
            "posting_type varchar, first_published date)"
        )
        con.execute(
            "insert into silver_postings values ('open', 'Data Engineer', 'ARBEIT', '2026-11-01'),"
            " ('closed', 'Old', 'ARBEIT', '2026-09-01'), ('azubi', 'Azubi', 'AUSBILDUNG', null)"
        )
        con.execute("create table silver_posting_texts (refnr varchar, description varchar)")
        con.execute(
            "insert into silver_posting_texts values ('open', 'SQL'), ('closed', 'Java'),"
            " ('azubi', 'Lernen')"
        )
        con.execute("create table silver_posting_history (refnr varchar, is_open boolean)")
        con.execute(
            "insert into silver_posting_history values ('open', true), ('closed', false),"
            " ('azubi', true)"
        )
    # Never read the real .env in tests.
    monkeypatch.setattr(auto, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return tmp_path


@pytest.fixture
def notes(monkeypatch):
    seen = []
    monkeypatch.setattr(auto, "notify", lambda title, message: seen.append(title))
    return seen


def use_settings(monkeypatch, **changes):
    settings = load_settings().model_copy(update=changes)
    monkeypatch.setattr(auto, "load_settings", lambda: settings)


def fail_if_called():
    raise AssertionError("no client should be created")


def api_error(kind, status):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages/batches")
    return kind("error", response=httpx2.Response(status, request=request), body=None)


class TestSubmitStep:
    def test_sends_open_postings_once(self, data_dir):
        client = FakeClient()
        auto.submit_step(data_dir, lambda: client)
        auto.submit_step(data_dir, lambda: client)

        assert len(client.batches.sent) == 1
        assert [r["custom_id"] for r in client.batches.sent[0]] == [custom_id("open")]

    def test_switched_off(self, data_dir, monkeypatch):
        use_settings(monkeypatch, daily=False)
        auto.submit_step(data_dir, fail_if_called)

    def test_no_api_key(self, data_dir, monkeypatch, caplog):
        monkeypatch.delenv("ANTHROPIC_API_KEY")
        with caplog.at_level(logging.WARNING):
            auto.submit_step(data_dir, fail_if_called)
        assert "no ANTHROPIC_API_KEY" in caplog.text

    def test_no_warehouse_yet(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auto, "load_dotenv", lambda *args, **kwargs: None)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        auto.submit_step(tmp_path, fail_if_called)

    def test_monthly_budget_reached_is_not_an_error(self, data_dir, monkeypatch, caplog, notes):
        use_settings(monkeypatch, monthly_budget_usd=0.0001)
        client = FakeClient()
        with caplog.at_level(logging.INFO):
            auto.submit_step(data_dir, lambda: client)
        assert client.batches.sent == [] and notes == []
        assert "budget" in caplog.text

    def test_rejected_key_alerts(self, data_dir, notes):
        client = FakeClient()

        def reject(requests):
            raise api_error(anthropic.AuthenticationError, 401)

        client.batches.create = reject
        auto.submit_step(data_dir, lambda: client)
        assert notes == ["SkillRadar: Claude API key rejected"]

    def test_other_api_errors_are_logged_and_retried_later(self, data_dir, notes, caplog):
        client = FakeClient()

        def overloaded(requests):
            raise api_error(anthropic.InternalServerError, 529)

        client.batches.create = overloaded
        with caplog.at_level(logging.ERROR):
            auto.submit_step(data_dir, lambda: client)
        assert notes == [] and "will retry" in caplog.text
        assert ExtractionStore(data_dir / "llm").pending() == []


class TestCollectStep:
    def test_nothing_pending_needs_no_client(self, data_dir):
        auto.collect_step(data_dir, fail_if_called)

    def test_saves_finished_answers(self, data_dir):
        client = FakeClient()
        auto.submit_step(data_dir, lambda: client)
        client.batches.finish("msgbatch_1", [succeeded(custom_id("open"))])

        auto.collect_step(data_dir, lambda: client)

        store = ExtractionStore(data_dir / "llm")
        assert store.pending() == [] and [r["refnr"] for r in store.results()] == ["open"]


class TestWaitStep:
    def test_nothing_pending_returns_at_once(self, data_dir):
        auto.wait_step(data_dir, fail_if_called, sleep=fail_if_called)

    def test_collects_when_the_batch_ends(self, data_dir):
        client = FakeClient()
        auto.submit_step(data_dir, lambda: client)
        waits = []

        def sleep(seconds):
            waits.append(seconds)
            if len(waits) == 3:  # the batch ends during the third wait
                client.batches.finish("msgbatch_1", [succeeded(custom_id("open"))])

        auto.wait_step(data_dir, lambda: client, sleep=sleep)

        assert len(waits) == 3
        store = ExtractionStore(data_dir / "llm")
        assert store.pending() == [] and len(store.results()) == 1

    def test_gives_up_after_the_limit(self, data_dir, caplog):
        client = FakeClient()
        auto.submit_step(data_dir, lambda: client)
        waits = []

        with caplog.at_level(logging.INFO):
            auto.wait_step(data_dir, lambda: client, sleep=waits.append)

        assert sum(waits) == auto.WAIT_MINUTES * 60
        assert len(ExtractionStore(data_dir / "llm").pending()) == 1
        assert "collected next time" in caplog.text
