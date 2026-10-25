"""Command line: uv run skillradar-snapshot [--city ...] [--term ...] [--notify] [--once-per-day]"""

import argparse
import logging
import signal
from datetime import UTC, datetime
from pathlib import Path

from skillradar.config import DATA_DIR, DEFAULT_CONFIG_PATH, SearchConfig, load_config
from skillradar.ingestion.bronze import BronzeStore
from skillradar.ingestion.client import JobsucheClient
from skillradar.ingestion.snapshot import RunSummary, run_snapshot
from skillradar.lock import AlreadyRunning, run_lock
from skillradar.notify import notify

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Save today's job postings to bronze.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--city", action="append", help="only this city (repeatable)")
    parser.add_argument("--term", action="append", help="only this search term (repeatable)")
    parser.add_argument("--notify", action="store_true", help="desktop alert if the run has errors")
    parser.add_argument(
        "--once-per-day", action="store_true", help="do nothing if today already has a full run"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        config = load_config(args.config).only(cities=args.city, terms=args.term)
    except ValueError as error:
        logger.error("bad config: %s", error)
        return 2

    stop_on_sigterm()
    try:
        with run_lock(args.data_dir / ".snapshot.lock"):
            today = datetime.now(UTC).date().isoformat()
            if args.once_per_day and BronzeStore(args.data_dir / "bronze").has_finished_run(today):
                logger.info("today (%s UTC) already has a full run, nothing to do", today)
                return 0
            full_scope = not (args.city or args.term)
            summary = _run(config, args.data_dir, full_scope)
    except AlreadyRunning as error:
        logger.error("%s", error)
        return 3
    except Exception:
        if args.notify:
            notify("SkillRadar run crashed", "See data/logs/snapshot.log")
        raise

    _log_summary(summary)
    if args.notify and summary.status != "ok":
        notify(f"SkillRadar run {summary.status}", f"{len(summary.errors)} errors, see run log")
    return 1 if summary.status == "failed" else 0


def stop_on_sigterm() -> None:
    """macOS sends SIGTERM at shutdown. Turn it into an exception so cleanup code runs."""

    def handler(signum: int, _frame: object) -> None:
        raise SystemExit(f"stopped by signal {signum}")

    signal.signal(signal.SIGTERM, handler)


def _run(config: SearchConfig, data_dir: Path, full_scope: bool) -> RunSummary:
    store = BronzeStore(data_dir / "bronze")
    with JobsucheClient(config.api) as client:
        return run_snapshot(config, client, store, full_scope=full_scope)


def _log_summary(summary: RunSummary) -> None:
    logger.info(
        "run %s %s: %d unique postings, %d new, %d details saved, %d errors",
        summary.run_id,
        summary.status,
        summary.unique_postings,
        summary.new_postings,
        summary.details_saved,
        len(summary.errors),
    )


if __name__ == "__main__":
    raise SystemExit(main())
