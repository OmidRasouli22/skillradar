"""Send postings to Claude in batches and read the answers.

submit: one batch with every posting that has no answer yet, saved as pending.
collect: for each pending batch that has ended, save the answers.
A batch can take hours, so the two steps are separate and survive restarts.
Nothing is sent that could go over the budget (see budget.py).
"""

import hashlib
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from skillradar.extract import budget
from skillradar.extract.prompt import PROMPT_VERSION, system_prompt, user_message
from skillradar.extract.schema import OUTPUT_SCHEMA, Extraction
from skillradar.extract.settings import LlmSettings
from skillradar.extract.store import ExtractionStore, PendingBatch
from skillradar.skills.taxonomy import Taxonomy
from skillradar.storage import Record

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class PostingText:
    refnr: str
    title: str
    description: str


@dataclass
class CollectSummary:
    still_running: int = 0
    batches_done: int = 0
    answers: dict[str, int] = field(default_factory=dict)
    retry_later: int = 0


def custom_id(refnr: str) -> str:
    """Batch ids allow only [A-Za-z0-9_-], so the refnr is hashed. Submit keeps the mapping."""
    return "p_" + hashlib.sha256(refnr.encode()).hexdigest()[:32]


def request_params(posting: PostingText, settings: LlmSettings, system: str) -> dict[str, Any]:
    return {
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user_message(posting.title, posting.description)}],
        "output_config": {
            "effort": settings.effort,
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
        },
    }


def read_answer(message: Any) -> tuple[str, dict[str, Any] | None]:
    """Status and checked answer. A refusal or a cut-off answer has no data."""
    if message.stop_reason == "refusal":
        return "refused", None
    if message.stop_reason == "max_tokens":
        return "max_tokens", None
    text = next((block.text for block in message.content if block.type == "text"), "")
    try:
        return "ok", Extraction.model_validate_json(text).model_dump()
    except ValidationError:
        return "invalid", None


def usage_of(message: Any) -> dict[str, int]:
    usage = message.usage
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }


def extract_one(
    client: Any,
    posting: PostingText,
    settings: LlmSettings,
    taxonomy: Taxonomy,
    store: ExtractionStore,
    clock: Clock = utc_now,
):
    """One posting without a batch, at full price. For trying the prompt."""
    params = request_params(posting, settings, system_prompt(taxonomy))
    room = budget.room_left(settings, store, budget.month_of(clock()))
    if budget.worst_case(params, settings, batch=False) > room:
        raise budget.OverBudget(f"not sent: only ${room:.4f} of this month's budget is left")
    message = client.messages.create(**params)
    usage = usage_of(message)
    store.save_try(
        {"refnr": posting.refnr, "model": settings.model, "at": clock().isoformat(), "usage": usage}
    )
    status, output = read_answer(message)
    return status, output, usage


def submit(
    client: Any,
    postings: Iterable[PostingText],
    settings: LlmSettings,
    taxonomy: Taxonomy,
    store: ExtractionStore,
    clock: Clock = utc_now,
) -> PendingBatch | None:
    done = store.done_refnrs(settings.model, PROMPT_VERSION) | store.pending_refnrs()
    todo = [p for p in postings if p.refnr not in done][: settings.batch_limit]
    if not todo:
        return None

    system = system_prompt(taxonomy)
    requests = [
        {"custom_id": custom_id(p.refnr), "params": request_params(p, settings, system)}
        for p in todo
    ]
    costs = [budget.worst_case(r["params"], settings, batch=True) for r in requests]
    room = budget.room_left(settings, store, budget.month_of(clock()))
    fits = budget.affordable(costs, room)
    if fits == 0:
        raise budget.OverBudget(f"not sent: only ${room:.4f} of this month's budget is left")
    if fits < len(todo):
        logger.info("budget: sending %d of %d postings", fits, len(todo))
    todo, requests = todo[:fits], requests[:fits]

    created = client.messages.batches.create(requests=requests)
    batch = PendingBatch(
        batch_id=created.id,
        created_at=clock().isoformat(),
        model=settings.model,
        prompt_version=PROMPT_VERSION,
        refnrs={custom_id(p.refnr): p.refnr for p in todo},
        max_cost_usd=sum(costs[:fits]),
    )
    store.save_pending(batch)
    logger.info("sent batch %s with %d postings", created.id, len(todo))
    return batch


def collect(client: Any, store: ExtractionStore, clock: Clock = utc_now) -> CollectSummary:
    summary = CollectSummary()
    for batch in store.pending():
        status = client.messages.batches.retrieve(batch.batch_id).processing_status
        if status != "ended":
            summary.still_running += 1
            continue

        results = []
        for item in client.messages.batches.results(batch.batch_id):
            refnr = batch.refnrs.get(item.custom_id)
            if refnr is None:
                logger.warning("unknown custom_id %s in batch %s", item.custom_id, batch.batch_id)
                continue
            if item.result.type != "succeeded":
                # errored, canceled or expired: not saved, so the next submit sends it again
                summary.retry_later += 1
                continue
            answer_status, output = read_answer(item.result.message)
            summary.answers[answer_status] = summary.answers.get(answer_status, 0) + 1
            results.append(_record(batch, refnr, answer_status, output, item.result.message, clock))

        store.finish(batch.batch_id, results)
        summary.batches_done += 1
    return summary


def _record(
    batch: PendingBatch, refnr: str, status: str, output: Any, message: Any, clock: Clock
) -> Record:
    return {
        "refnr": refnr,
        "batch_id": batch.batch_id,
        "model": batch.model,
        "prompt_version": batch.prompt_version,
        "extracted_at": clock().isoformat(),
        "status": status,
        "output": output,
        "usage": usage_of(message),
    }
