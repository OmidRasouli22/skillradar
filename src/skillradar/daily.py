"""Command line: uv run skillradar-daily

The scheduled job: snapshot once per day, then rebuild silver when there is new data.
"""

import argparse
import logging
from pathlib import Path

from skillradar.config import DATA_DIR
from skillradar.ingestion import cli as snapshot_cli
from skillradar.logs import setup_logging
from skillradar.notify import notify
from skillradar.transform.runner import TransformError, build, warehouse_path

logger = logging.getLogger(__name__)

SNAPSHOT_FAILED = 1


def needs_transform(data_dir: Path) -> bool:
    """True if a run finished after the last build, so a failed build is retried later."""
    warehouse = warehouse_path(data_dir)
    run_logs = list((data_dir / "bronze" / "runs").glob("run_*.json"))
    if not run_logs:
        return False
    if not warehouse.exists():
        return True
    newest_run = max(path.stat().st_mtime for path in run_logs)
    return newest_run > warehouse.stat().st_mtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily snapshot, then rebuild silver.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args(argv)
    setup_logging()
    data_dir = args.data_dir.resolve()

    code = snapshot_cli.main(["--data-dir", str(data_dir), "--notify", "--once-per-day"])
    if code == SNAPSHOT_FAILED:
        return code

    if not needs_transform(data_dir):
        logger.info("silver is up to date")
        return code

    logger.info("new data, rebuilding silver")
    try:
        build(data_dir)
    except TransformError as error:
        logger.error("transform failed: %s", error)
        notify("SkillRadar transform failed", "See data/logs/snapshot.log")
        return 1
    logger.info("silver rebuilt")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
