"""The pipeline health page: is the data fresh, did the last runs and tests pass, what did
Claude cost, how complete are the answers, and how good is the extraction.

Everything comes from files the pipeline writes anyway: run logs, dbt's run_results.json,
the Claude batch files, the gold Parquet files and the evaluation report. The warehouse is
never opened, so the page can't block a build.

The result is published on the public site, so it holds counts, dates and costs only:
no file paths, no error texts and no batch ids.
"""

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from skillradar.evaluate.cli import report_path
from skillradar.extract import budget
from skillradar.extract.prompt import PROMPT_VERSION
from skillradar.extract.settings import LlmSettings, load_settings
from skillradar.extract.store import ExtractionStore
from skillradar.transform.runner import serve_dir, table_counts_path

logger = logging.getLogger(__name__)

RUNS_SHOWN = 14
BATCHES_SHOWN = 10
# The daily job runs once a day. A day late is "late", two days late is "stale".
FRESH_HOURS = 30
LATE_HOURS = 54
RUN_FIELDS = (
    "status",
    "full_scope",
    "queries",
    "failed_queries",
    "unique_postings",
    "new_postings",
    "details_saved",
    "failed_details",
)


def build_health(data_dir: Path, now: datetime | None = None) -> dict:
    """Each part is built on its own: one that fails is empty (and logged), so the health
    page can never stop the site from being published."""
    now = now or datetime.now(UTC)
    runs = _part("runs", lambda: recent_runs(data_dir / "bronze" / "runs")) or []
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "thresholds": {"fresh_hours": FRESH_HOURS, "late_hours": LATE_HOURS},
        "freshness": freshness(runs, now),
        "runs": runs[:RUNS_SHOWN],
        "layers": _part("layers", lambda: layers(data_dir)),
        "tests": _part(
            "tests", lambda: dbt_results(data_dir / "dbt" / "target" / "run_results.json")
        ),
        "claude": _part("claude", lambda: claude(data_dir, now)),
        "coverage": _part("coverage", lambda: coverage(serve_dir(data_dir))),
        "evaluation": _part("evaluation", lambda: evaluation(report_path(data_dir))),
    }


def _part(name: str, build: Callable[[], Any]) -> Any:
    try:
        return build()
    except Exception:
        logger.exception("health: the %s part failed", name)
        return None


def recent_runs(folder: Path) -> list[dict]:
    """The newest runs first, with their counts (never the error texts)."""
    runs = []
    for path in sorted(folder.glob("run_*.json"), reverse=True):
        record = _read_json(path)
        if not isinstance(record, dict) or not isinstance(record.get("run_id"), str):
            continue
        run = {"run_id": record["run_id"], "started_at": record.get("started_at")}
        run["minutes"] = _minutes(record.get("started_at"), record.get("finished_at"))
        run |= {field: record.get(field) for field in RUN_FIELDS}
        run["errors"] = len(record.get("errors") or [])
        runs.append(run)
    return runs


def freshness(runs: list[dict], now: datetime) -> dict:
    """How long ago the last run that saved data started."""
    good = [r for r in runs if r["status"] in ("ok", "partial") and r["started_at"]]
    if not good:
        return {"last_success": None, "hours": None, "state": "stale"}
    last = good[0]["started_at"]
    hours = (now - datetime.fromisoformat(last)).total_seconds() / 3600
    state = "fresh" if hours <= FRESH_HOURS else "late" if hours <= LATE_HOURS else "stale"
    return {"last_success": last, "hours": round(hours, 1), "state": state}


def layers(data_dir: Path) -> dict:
    bronze = data_dir / "bronze"
    files = {}
    for kind, pattern in (
        ("search", "search/*/run_*.jsonl.gz"),
        ("details", "details/*/run_*.jsonl"),
        ("runs", "runs/run_*.json"),
    ):
        found = list(bronze.glob(pattern))
        size = sum(path.stat().st_size for path in found)
        files[kind] = {"files": len(found), "megabytes": round(size / 1_000_000, 1)}
    counts = _read_json(table_counts_path(data_dir))
    tables = counts if isinstance(counts, dict) else {}
    return {
        "bronze": files,
        "silver": {k: v for k, v in sorted(tables.items()) if k.startswith("silver_")},
        "gold": {k: v for k, v in sorted(tables.items()) if k.startswith("gold_")},
    }


def dbt_results(path: Path) -> dict | None:
    """Models and tests of the last dbt build."""
    results = _read_json(path)
    if not isinstance(results, dict):
        return None
    models: dict[str, int] = {}
    tests: dict[str, int] = {}
    failures = []
    for item in results.get("results", []):
        unique_id, status = str(item.get("unique_id", "")), str(item.get("status", ""))
        group = tests if unique_id.startswith("test.") else models
        group[status] = group.get(status, 0) + 1
        if status in ("fail", "error", "warn"):
            # test.<project>.<name>.<hash>: the name is enough to find it.
            parts = unique_id.split(".")
            failures.append({"name": parts[2] if len(parts) > 2 else unique_id, "status": status})
    return {
        "finished_at": results.get("metadata", {}).get("generated_at"),
        "seconds": round(float(results.get("elapsed_time", 0)), 1),
        "models": models,
        "tests": tests,
        "failures": failures,
    }


def claude(data_dir: Path, now: datetime) -> dict:
    settings = load_settings()
    store = ExtractionStore(data_dir / "llm")
    results = store.results()
    month = budget.month_of(now)
    try:
        spent = round(budget.spent(settings, store, month), 2)
    except budget.OverBudget:
        spent = None  # an answer from a model without a price
    by_batch: dict[str, list[dict]] = {}
    for record in results:
        by_batch.setdefault(str(record.get("batch_id")), []).append(record)
    batches = []
    for path in sorted((data_dir / "llm" / "batches" / "done").glob("*.json"), reverse=True):
        batch = _read_json(path)
        if not isinstance(batch, dict):
            continue
        answers = by_batch.get(str(batch.get("batch_id")), [])
        batches.append(
            {
                "created_at": batch.get("created_at"),
                "postings": len(batch.get("refnrs", {})),
                "answers": sum(1 for a in answers if a["status"] == "ok"),
                "failed": sum(1 for a in answers if a["status"] != "ok"),
                "cost_usd": _batch_cost(settings, answers),
            }
        )
    batches.sort(key=lambda b: b["created_at"] or "", reverse=True)
    pending = store.pending()
    return {
        "model": settings.model,
        "prompt_version": PROMPT_VERSION,
        "month": month,
        "spent_usd": spent,
        "budget_usd": settings.monthly_budget_usd,
        "pending_batches": len(pending),
        "pending_postings": sum(len(b.refnrs) for b in pending),
        "answers": sum(1 for r in results if r["status"] == "ok"),
        "failed_answers": sum(1 for r in results if r["status"] != "ok"),
        "batches": batches[:BATCHES_SHOWN],
    }


def coverage(folder: Path) -> dict | None:
    """Open postings with an answer now, and per week (gold_meta and gold_weeks)."""
    meta_file, weeks_file = folder / "gold_meta.parquet", folder / "gold_weeks.parquet"
    if not meta_file.exists():
        return None
    with duckdb.connect() as con:
        meta = con.execute(
            "select as_of, open_postings::bigint, postings_with_answers::bigint, "
            "tech_postings::bigint from read_parquet(?)",
            [str(meta_file)],
        ).fetchone()
        weeks = []
        if weeks_file.exists():
            weeks = con.execute(
                # Plain numbers, so the result can be written as JSON.
                "select week_start, week_ended, open_postings::bigint, tech_postings::bigint, "
                "coverage::double from read_parquet(?) order by week_start",
                [str(weeks_file)],
            ).fetchall()
    as_of, open_postings, answered, tech = meta
    return {
        "as_of": str(as_of) if as_of else None,
        "open_postings": open_postings,
        "with_answer": answered,
        "tech_postings": tech,
        "share": round(answered / open_postings, 4) if open_postings else None,
        "weeks": [
            {
                "week_start": str(week),
                "ended": ended,
                "open_postings": open_,
                "tech_postings": tech_,
                "coverage": share,
            }
            for week, ended, open_, tech_, share in weeks
        ],
    }


def evaluation(path: Path) -> dict | None:
    """The extraction's scores. Numbers from unchecked drafts are never shown."""
    report = _read_json(path)
    if not isinstance(report, dict):
        return None
    sample = report.get("sample", {})
    summary: dict[str, Any] = {"generated_at": report.get("generated_at"), "sample": sample}
    if report.get("includes_drafts") or not sample.get("verified"):
        summary["systems"] = []
        return summary
    summary["labels"] = report.get("labels")
    summary["systems"] = [
        {
            "id": system["id"],
            "name": system["name"],
            "postings": system["postings"],
            "skills": _pick(system.get("skills"), ("precision", "recall", "f1")),
            "fields": {
                field: (system.get(field) or {}).get("accuracy")
                for field in ("role", "seniority", "remote", "required")
            },
        }
        for system in report.get("systems", [])
        if system["id"] == "keywords" or system["id"].endswith("/counted")
    ]
    return summary


def _pick(scores: dict | None, keys: tuple[str, ...]) -> dict | None:
    return {key: scores[key] for key in keys} if scores else None


def _batch_cost(settings: LlmSettings, answers: list[dict]) -> float | None:
    try:
        return round(sum(budget.answer_cost(settings, a) for a in answers), 4)
    except budget.OverBudget:
        return None


def _minutes(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    seconds = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
    return round(seconds / 60, 1)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("health: cannot read %s: %s", path.name, error)
        return None
