"""Command line: uv run skillradar-snapshot [--city ...] [--term ...]"""

import argparse
import logging
from pathlib import Path

from skillradar.config import DATA_DIR, DEFAULT_CONFIG_PATH, load_config
from skillradar.ingestion.bronze import BronzeStore
from skillradar.ingestion.client import JobsucheClient
from skillradar.ingestion.snapshot import run_snapshot

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Save today's job postings to bronze.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--city", action="append", help="only this city (repeatable)")
    parser.add_argument("--term", action="append", help="only this search term (repeatable)")
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

    store = BronzeStore(args.data_dir / "bronze")
    with JobsucheClient(config.api) as client:
        summary = run_snapshot(config, client, store)

    logger.info(
        "run %s %s: %d unique postings, %d new, %d details saved, %d errors",
        summary.run_id,
        summary.status,
        summary.unique_postings,
        summary.new_postings,
        summary.details_saved,
        len(summary.errors),
    )
    return 1 if summary.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
