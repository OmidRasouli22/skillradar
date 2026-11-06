"""Command line: uv run skillradar-extract estimate|try|submit|collect|status|quality

estimate, status and quality are free. try, submit and collect call the Claude API.
try and submit never send more than budget_usd in config/llm.yaml allows.
The API key is read from .env (ANTHROPIC_API_KEY) or the environment.
"""

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import anthropic
import duckdb
from dotenv import load_dotenv

from skillradar.config import DATA_DIR, PROJECT_ROOT
from skillradar.extract import budget
from skillradar.extract.batch import PostingText, collect, extract_one, submit
from skillradar.extract.prompt import PROMPT_VERSION, system_prompt
from skillradar.extract.quality import summary
from skillradar.extract.settings import load_settings
from skillradar.extract.store import ExtractionStore
from skillradar.logs import setup_logging
from skillradar.skills.taxonomy import load_taxonomy
from skillradar.transform.runner import warehouse_path

logger = logging.getLogger(__name__)

# Rough numbers for the estimate: characters per token, and answer tokens per posting
# (the JSON plus some thinking at low effort).
CHARS_PER_TOKEN = 3.5
ANSWER_TOKENS = 600

POSTINGS_SQL = """
    select t.refnr, coalesce(p.title, ''), t.description
    from silver_posting_texts t
    join silver_postings p using (refnr)
    where p.posting_type is distinct from 'AUSBILDUNG' {only_open}
    order by p.first_published desc nulls last, t.refnr
"""
ONLY_OPEN = "and t.refnr in (select refnr from silver_posting_history where is_open)"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract skills from postings with Claude.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    commands = parser.add_subparsers(dest="command", required=True)
    estimate = commands.add_parser("estimate", help="postings to do and a rough cost (free)")
    estimate.add_argument("--open-only", action="store_true", help="only open postings")
    try_one = commands.add_parser("try", help="extract one posting now, at full price")
    try_one.add_argument("--refnr", required=True)
    send = commands.add_parser("submit", help="send postings without an answer as a batch")
    send.add_argument("--limit", type=int, help="send at most this many postings")
    send.add_argument("--open-only", action="store_true", help="only open postings")
    commands.add_parser("collect", help="save answers from finished batches")
    commands.add_parser("status", help="pending batches and saved answers (free)")
    commands.add_parser("quality", help="quality numbers per prompt version (free)")
    return parser.parse_args(argv)


def load_postings(warehouse: Path, only_open: bool = False) -> list[PostingText]:
    sql = POSTINGS_SQL.format(only_open=ONLY_OPEN if only_open else "")
    with duckdb.connect(str(warehouse), read_only=True) as con:
        return [PostingText(*row) for row in con.execute(sql).fetchall()]


def main(argv: list[str] | None = None, client: Any = None) -> int:
    args = parse_args(argv)
    setup_logging()
    load_dotenv(PROJECT_ROOT / ".env")

    data_dir = args.data_dir.resolve()
    settings = load_settings()
    store = ExtractionStore(data_dir / "llm")

    if args.command == "status":
        return _status(store, settings)
    if args.command == "quality":
        return _quality(store)

    warehouse = warehouse_path(data_dir)
    if args.command in ("estimate", "try", "submit") and not warehouse.exists():
        print(f"{warehouse} not found, run skillradar-transform first", file=sys.stderr)
        return 1

    if args.command == "estimate":
        return _estimate(load_postings(warehouse, args.open_only), store, settings)

    try:
        client = client or anthropic.Anthropic()
        if args.command == "try":
            return _try(client, load_postings(warehouse), args.refnr, settings, store)
        if args.command == "submit":
            if args.limit:
                settings = settings.model_copy(update={"batch_limit": args.limit})
            postings = load_postings(warehouse, args.open_only)
            batch = submit(client, postings, settings, load_taxonomy(), store)
            print(
                f"sent batch {batch.batch_id}: {len(batch.refnrs)} postings"
                if batch
                else "nothing to send"
            )
            return 0
        summary = collect(client, store)
        print(
            f"done: {summary.batches_done} batches {summary.answers}, "
            f"still running: {summary.still_running}, retry later: {summary.retry_later}"
        )
        return 0
    except budget.OverBudget as error:
        print(f"{error} (budget_usd in config/llm.yaml)", file=sys.stderr)
        return 1
    except anthropic.AuthenticationError:
        print("API key missing or wrong: set ANTHROPIC_API_KEY in .env", file=sys.stderr)
        return 1
    except anthropic.APIError as error:
        print(f"Claude API error: {error}", file=sys.stderr)
        return 1


def _estimate(postings: list[PostingText], store: ExtractionStore, settings) -> int:
    done = store.done_refnrs(settings.model, PROMPT_VERSION) | store.pending_refnrs()
    todo = [p for p in postings if p.refnr not in done]
    system_tokens = len(system_prompt(load_taxonomy())) / CHARS_PER_TOKEN
    posting_tokens = sum(len(p.title) + len(p.description) for p in todo) / CHARS_PER_TOKEN
    input_tokens = int(posting_tokens + system_tokens * len(todo))
    output_tokens = ANSWER_TOKENS * len(todo)

    print(
        f"{len(todo)} postings without an answer (model {settings.model}, prompt {PROMPT_VERSION})"
    )
    print(f"about {input_tokens / 1e6:.1f}M input and {output_tokens / 1e6:.1f}M output tokens\n")
    print("rough batch cost, before caching:")
    for model in settings.prices:
        mark = "  <- configured" if model == settings.model else ""
        print(
            f"  {model:<20} ${settings.batch_cost(input_tokens, output_tokens, model):8.2f}{mark}"
        )
    measured = [
        budget.usage_cost(r["usage"], settings.prices[settings.model], batch=True)
        for r in store.results()
        if r["model"] == settings.model
    ]
    if measured:
        per_posting = sum(measured) / len(measured)
        print(
            f"\nmeasured so far: ${per_posting:.6f} per posting, "
            f"so about ${per_posting * len(todo):.2f} for these"
        )
    print()
    _print_budget(store, settings)
    return 0


def _try(client: Any, postings: list[PostingText], refnr: str, settings, store) -> int:
    posting = next((p for p in postings if p.refnr == refnr), None)
    if posting is None:
        print(f"no posting {refnr}", file=sys.stderr)
        return 1
    status, output, usage = extract_one(client, posting, settings, load_taxonomy(), store)
    print(f"{posting.title}\nstatus: {status}, usage: {usage}")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if status == "ok" else 1


def _status(store: ExtractionStore, settings) -> int:
    for batch in store.pending():
        print(f"pending {batch.batch_id}: {len(batch.refnrs)} postings, sent {batch.created_at}")
    results = store.results()
    counts = Counter((r["model"], r["prompt_version"], r["status"]) for r in results)
    for (model, version, status), count in sorted(counts.items()):
        print(f"saved {model} {version} {status}: {count}")
    if not results and not store.pending():
        print("no batches yet")
    _print_budget(store, settings)
    return 0


def _quality(store: ExtractionStore) -> int:
    groups = summary(store.results(), load_taxonomy())
    for (model, version), numbers in groups.items():
        print(f"{model} {version}")
        for name, value in numbers.items():
            print(f"  {name:<22} {value}")
    if not groups:
        print("no answers yet")
    return 0


def _print_budget(store: ExtractionStore, settings) -> None:
    spent = budget.spent(settings, store)
    print(
        f"budget ${settings.budget_usd:.2f}, spent ${spent:.4f} "
        f"(pending batches at worst case), left ${settings.budget_usd - spent:.4f}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
