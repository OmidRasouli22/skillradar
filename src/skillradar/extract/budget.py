"""Monthly spending cap for the Claude API.

Before a request is sent, its worst case cost is added to what is already spent this
month (UTC). If the total would go over monthly_budget_usd in config/llm.yaml, it is
not sent.

Spent this month = answers saved this month + try calls this month + worst case of all
pending batches (they count until they are collected, whatever month they were sent).

Worst case for one request: every byte of the request is one token (a token is at
least one byte), all of it is written to the cache, and the answer uses max_tokens.
"""

import json
from datetime import UTC, datetime
from typing import Any

from skillradar.extract.settings import LlmSettings, Price
from skillradar.extract.store import ExtractionStore
from skillradar.storage import Record

CACHE_WRITE = 1.25  # times the input price
CACHE_READ = 0.1
# Hidden tokens the API adds, e.g. for the output schema.
OVERHEAD_TOKENS = 2000
# Haiku 5.5 costs double above this prompt size. Counted for every model to be safe.
LONG_PROMPT_TOKENS = 100_000


class OverBudget(Exception):
    pass


def usage_cost(usage: dict[str, int], price: Price, batch: bool) -> float:
    """USD for one answer, from the usage the API returned."""
    input_usd = (
        usage.get("input_tokens", 0)
        + usage.get("cache_write_tokens", 0) * CACHE_WRITE
        + usage.get("cache_read_tokens", 0) * CACHE_READ
    ) * price.input
    total = (input_usd + usage.get("output_tokens", 0) * price.output) / 1_000_000
    return total / 2 if batch else total


def worst_case(params: dict[str, Any], settings: LlmSettings, batch: bool) -> float:
    """Most one request with these params can cost."""
    prompt_tokens = len(json.dumps(params, ensure_ascii=False).encode()) + OVERHEAD_TOKENS
    usage = {"cache_write_tokens": prompt_tokens, "output_tokens": params["max_tokens"]}
    cost = usage_cost(usage, settings.prices[params["model"]], batch)
    return cost * 2 if prompt_tokens > LONG_PROMPT_TOKENS else cost


def month_of(moment: datetime) -> str:
    """The budget month, e.g. "2026-11"."""
    return moment.astimezone(UTC).strftime("%Y-%m")


def spent(settings: LlmSettings, store: ExtractionStore, month: str) -> float:
    answers = [r for r in store.results() if r["extracted_at"].startswith(month)]
    tries = [r for r in store.tries() if r["at"].startswith(month)]
    total = sum(_cost(settings, r, batch=True) for r in answers)
    total += sum(_cost(settings, r, batch=False) for r in tries)
    return total + sum(batch.max_cost_usd for batch in store.pending())


def room_left(settings: LlmSettings, store: ExtractionStore, month: str) -> float:
    return settings.monthly_budget_usd - spent(settings, store, month)


def affordable(costs: list[float], room: float) -> int:
    """How many of these requests fit in the room left, in order."""
    total = 0.0
    for count, cost in enumerate(costs):
        total += cost
        if total > room:
            return count
    return len(costs)


def _cost(settings: LlmSettings, record: Record, batch: bool) -> float:
    price = settings.prices.get(record["model"])
    if price is None:
        raise OverBudget(f"no price for {record['model']} in config/llm.yaml, cannot count spend")
    return usage_cost(record["usage"], price, batch)
