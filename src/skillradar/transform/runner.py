"""Run the dbt project in transform/ against the local data folder."""

import os
from pathlib import Path

from dbt.cli.main import dbtRunner

from skillradar.config import PROJECT_ROOT

DBT_PROJECT_DIR = PROJECT_ROOT / "transform"


class TransformError(Exception):
    pass


def warehouse_path(data_dir: Path) -> Path:
    return data_dir / "warehouse.duckdb"


def build(data_dir: Path, select: str | None = None) -> None:
    """Build and test the dbt models. Raises TransformError if anything fails."""
    data_dir = data_dir.resolve()
    bronze = data_dir / "bronze"
    _check_path(data_dir)
    if not any(bronze.glob("details/snapshot_date=*/run_*.jsonl")):
        raise TransformError(f"no details files in {bronze}, run skillradar-snapshot first")

    # dbt reads these in profiles.yml and in the bronze_files macro.
    os.environ["SKILLRADAR_BRONZE_DIR"] = str(bronze)
    os.environ["SKILLRADAR_WAREHOUSE"] = str(warehouse_path(data_dir))
    os.environ["DO_NOT_TRACK"] = "1"

    args = [
        "build",
        "--project-dir", str(DBT_PROJECT_DIR),
        "--profiles-dir", str(DBT_PROJECT_DIR),
        "--target-path", str(data_dir / "dbt" / "target"),
        "--log-path", str(data_dir / "dbt" / "logs"),
    ]  # fmt: skip
    if select:
        args += ["--select", select]

    result = dbtRunner().invoke(args)
    if not result.success:
        raise TransformError("dbt build failed, see the output above")


def _check_path(path: Path) -> None:
    # The path is put inside SQL strings, so a quote could break out of them.
    if "'" in str(path):
        raise TransformError(f"data folder path must not contain a quote: {path}")
