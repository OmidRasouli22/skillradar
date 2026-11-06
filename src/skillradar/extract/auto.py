"""Claude's part of the daily job: collect finished batches, then send new open postings.

Both steps are safe to run every hour. collect is free, and submit only sends postings
that have no answer and are not in a batch yet. Problems are logged and never raised,
so the snapshot and silver keep working when the API or the budget says no.
"""

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

from skillradar.config import PROJECT_ROOT
from skillradar.extract import budget
from skillradar.extract.batch import collect, submit
from skillradar.extract.postings import load_postings
from skillradar.extract.settings import LlmSettings, load_settings
from skillradar.extract.store import ExtractionStore
from skillradar.notify import notify
from skillradar.skills.taxonomy import load_taxonomy
from skillradar.transform.runner import warehouse_path

logger = logging.getLogger(__name__)

ClientFactory = Callable[[], Any]


def collect_step(data_dir: Path, make_client: ClientFactory = anthropic.Anthropic) -> None:
    store = ExtractionStore(data_dir / "llm")
    if not store.pending() or not _ready(load_settings()):
        return
    _call(lambda: _collect(make_client(), store))


def submit_step(data_dir: Path, make_client: ClientFactory = anthropic.Anthropic) -> None:
    settings = load_settings()
    warehouse = warehouse_path(data_dir)
    if not _ready(settings) or not warehouse.exists():
        return
    store = ExtractionStore(data_dir / "llm")
    postings = load_postings(warehouse, only_open=True)
    _call(lambda: _submit(make_client(), postings, settings, store))


def _collect(client: Any, store: ExtractionStore) -> None:
    summary = collect(client, store)
    logger.info(
        "claude: collected %d batches %s, still running %d, retry later %d",
        summary.batches_done,
        summary.answers,
        summary.still_running,
        summary.retry_later,
    )


def _submit(client: Any, postings, settings: LlmSettings, store: ExtractionStore) -> None:
    batch = submit(client, postings, settings, load_taxonomy(), store)
    if batch is None:
        logger.info("claude: no new postings to send")


def _ready(settings: LlmSettings) -> bool:
    if not settings.daily:
        logger.info("claude: daily extraction is off (daily in config/llm.yaml)")
        return False
    load_dotenv(PROJECT_ROOT / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.warning("claude: no ANTHROPIC_API_KEY in .env, extraction skipped")
        return False
    return True


def _call(step: Callable[[], None]) -> None:
    try:
        step()
    except budget.OverBudget as error:
        # Not an error: the rest waits for next month or for the next hourly check.
        logger.info("claude: %s", error)
    except anthropic.AuthenticationError:
        logger.error("claude: API key was rejected")
        notify("SkillRadar: Claude API key rejected", "Check ANTHROPIC_API_KEY in .env")
    except anthropic.APIError as error:
        # Usually short outages or rate limits; the next hourly check tries again.
        logger.error("claude: API error, will retry next check: %s", error)
