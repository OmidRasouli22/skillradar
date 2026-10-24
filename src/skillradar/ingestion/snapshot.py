"""One daily run: search all queries, fetch details for new postings, save to bronze."""

import logging
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from skillradar.config import SearchConfig
from skillradar.ingestion.bronze import BronzeStore, Record, RunKey
from skillradar.ingestion.client import JobsucheError
from skillradar.ingestion.models import Posting, refnr_of

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]

PROGRESS_EVERY = 250


class JobSource(Protocol):
    def search(self, term: str, city: str, radius_km: int) -> Iterator[Posting]: ...

    def details(self, refnr: str) -> Posting | None: ...


@dataclass
class RunSummary:
    run_id: str
    started_at: str
    finished_at: str | None = None
    status: str = "running"
    recovered_files: int = 0
    queries: int = 0
    failed_queries: int = 0
    postings_seen: int = 0
    invalid_postings: int = 0
    unique_postings: int = 0
    new_postings: int = 0
    details_saved: int = 0
    details_gone: int = 0
    failed_details: int = 0
    errors: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        logger.warning(message)
        self.errors.append(message)


def utc_now() -> datetime:
    return datetime.now(UTC)


def run_snapshot(
    config: SearchConfig, source: JobSource, store: BronzeStore, clock: Clock = utc_now
) -> RunSummary:
    run = RunKey(clock())
    summary = RunSummary(run_id=run.run_id, started_at=run.started_at.isoformat())
    try:
        summary.recovered_files = store.recover_unfinished()
        refnrs = _search_all(config, source, store, run, summary)
        _fetch_new_details(source, store, run, refnrs, summary)
        summary.status = _status(summary)
    except BaseException as error:
        # BaseException also covers Ctrl+C and the stop signal at shutdown.
        summary.status = "failed"
        summary.add_error(f"run stopped: {error!r}")
        raise
    finally:
        summary.finished_at = clock().isoformat()
        store.write_run_log(run, asdict(summary))
    return summary


def _search_all(
    config: SearchConfig, source: JobSource, store: BronzeStore, run: RunKey, summary: RunSummary
) -> set[str]:
    records: list[Record] = []
    refnrs: set[str] = set()

    for term, city in config.queries():
        summary.queries += 1
        try:
            postings = list(source.search(term, city, config.radius_km))
        except JobsucheError as error:
            summary.failed_queries += 1
            summary.add_error(f"search {term!r} in {city!r}: {error}")
            continue

        for posting in postings:
            summary.postings_seen += 1
            refnr = refnr_of(posting)
            if refnr is None:
                summary.invalid_postings += 1
                continue
            refnrs.add(refnr)
            records.append({"run_id": run.run_id, "term": term, "city": city, "posting": posting})

    # An empty file would look like "no open postings today", so skip it when all failed.
    if summary.failed_queries < summary.queries:
        store.write_search(run, records)
    summary.unique_postings = len(refnrs)
    return refnrs


def _fetch_new_details(
    source: JobSource, store: BronzeStore, run: RunKey, refnrs: set[str], summary: RunSummary
) -> None:
    new_refnrs = sorted(refnrs - store.known_refnrs())
    summary.new_postings = len(new_refnrs)
    if not new_refnrs:
        return

    logger.info("fetching details for %d new postings", len(new_refnrs))
    with store.details_writer(run) as write:
        for done, refnr in enumerate(new_refnrs, start=1):
            if done % PROGRESS_EVERY == 0:
                logger.info("details %d/%d", done, len(new_refnrs))
            try:
                details = source.details(refnr)
            except JobsucheError as error:
                # Not saved, so the next run tries again.
                summary.failed_details += 1
                summary.add_error(f"details {refnr}: {error}")
                continue

            if details is None:
                summary.details_gone += 1
            else:
                summary.details_saved += 1
            write({"run_id": run.run_id, "refnr": refnr, "details": details})


def _status(summary: RunSummary) -> str:
    if summary.queries == 0 or summary.failed_queries == summary.queries:
        return "failed"
    if summary.errors:
        return "partial"
    return "ok"
