"""Command line: uv run skillradar-daily

The scheduled job, every hour while the Mac is on:
1. snapshot once per day
2. collect Claude's finished batches
3. rebuild silver when there is new data (postings or answers)
4. send new open postings to Claude, within the monthly budget
"""

import argparse
import logging
from pathlib import Path

from skillradar.config import DATA_DIR
from skillradar.extract import auto
from skillradar.ingestion import cli as snapshot_cli
from skillradar.logs import setup_logging
from skillradar.notify import notify
from skillradar.transform.runner import TransformError, build, warehouse_path

logger = logging.getLogger(__name__)

SNAPSHOT_FAILED = 1


def needs_transform(data_dir: Path) -> bool:
    """True if a run or Claude's answers came after the last build.

    A failed build is retried on the next check.
    """
    warehouse = warehouse_path(data_dir)
    run_logs = list((data_dir / "bronze" / "runs").glob("run_*.json"))
    if not run_logs:
        return False
    if not warehouse.exists():
        return True
    answers = list((data_dir / "llm" / "extractions").glob("*.jsonl"))
    newest = max(path.stat().st_mtime for path in [*run_logs, *answers])
    return newest > warehouse.stat().st_mtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily snapshot, then rebuild silver.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args(argv)
    setup_logging()
    data_dir = args.data_dir.resolve()

    code = snapshot_cli.main(["--data-dir", str(data_dir), "--notify", "--once-per-day"])
    if code == SNAPSHOT_FAILED:
        return code

    _claude_step(auto.collect_step, data_dir)

    if needs_transform(data_dir):
        logger.info("new data, rebuilding silver")
        try:
            build(data_dir)
        except TransformError as error:
            logger.error("transform failed: %s", error)
            notify("SkillRadar transform failed", "See data/logs/snapshot.log")
            return 1
        logger.info("silver rebuilt")
    else:
        logger.info("silver is up to date")

    _claude_step(auto.submit_step, data_dir)
    return code


def _claude_step(step, data_dir: Path) -> None:
    """Run a Claude step. A bug there must not stop the snapshot or silver."""
    try:
        step(data_dir)
    except Exception:
        logger.exception("claude step %s failed", step.__name__)


if __name__ == "__main__":
    raise SystemExit(main())
