"""Run the dbt project in transform/ against the local data folder."""

import json
import os
import re
from pathlib import Path

import duckdb
from dbt.cli.main import dbtRunner

from skillradar.config import PROJECT_ROOT
from skillradar.storage import atomic_write, make_private_dir

DBT_PROJECT_DIR = PROJECT_ROOT / "transform"
TABLE_NAME = re.compile(r"(silver|gold)_[a-z0-9_]{1,60}")


class TransformError(Exception):
    pass


def warehouse_path(data_dir: Path) -> Path:
    return data_dir / "warehouse.duckdb"


def serve_dir(data_dir: Path) -> Path:
    """Gold tables as Parquet files, read by the web API."""
    return data_dir / "serve"


def build(data_dir: Path, select: str | None = None) -> None:
    """Build and test the dbt models. Raises TransformError if anything fails."""
    data_dir = data_dir.resolve()
    bronze = data_dir / "bronze"
    _check_path(data_dir)
    for pattern in (
        "search/snapshot_date=*/run_*.jsonl.gz",
        "details/snapshot_date=*/run_*.jsonl",
        "runs/run_*.json",
    ):
        if not any(bronze.glob(pattern)):
            raise TransformError(f"no {pattern} in {bronze}, run skillradar-snapshot first")

    # dbt reads these in profiles.yml, the bronze_files macro and the skill models.
    os.environ["SKILLRADAR_BRONZE_DIR"] = str(bronze)
    os.environ["SKILLRADAR_LLM_DIR"] = str(data_dir / "llm")
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
    export_gold(data_dir)


def table_counts_path(data_dir: Path) -> Path:
    """Rows per silver and gold table after the last build, for the health page."""
    return serve_dir(data_dir) / "table_counts.json"


def export_gold(data_dir: Path) -> None:
    """Copy every gold table to a Parquet file, and count the rows of every table.

    The web API reads these files and never opens the warehouse, so a running page can't
    block the daily build. Each file is written next to the old one and then renamed, so
    the API never sees half a file.
    """
    folder = serve_dir(data_dir)
    make_private_dir(folder)
    # Same settings as dbt's connection, which is still open in this process: DuckDB
    # refuses a read-only connection next to it. Nothing is written here.
    with duckdb.connect(str(warehouse_path(data_dir))) as con:
        tables = [
            name
            for (name,) in con.execute(
                "select table_name from information_schema.tables "
                "where table_type = 'BASE TABLE' order by table_name"
            ).fetchall()
            # Names go into SQL below, so only plain dbt model names are used.
            if TABLE_NAME.fullmatch(name)
        ]
        counts = {}
        for table in tables:
            sql = f'select count(*) from "{table}"'  # noqa: S608 - checked name
            counts[table] = con.execute(sql).fetchone()[0]
            if table.startswith("gold_"):
                temp = folder / f".{table}.parquet.tmp"
                con.execute(f"copy \"{table}\" to '{temp}' (format parquet)")
                os.replace(temp, folder / f"{table}.parquet")
    atomic_write(table_counts_path(data_dir), json.dumps(counts, indent=2).encode("utf-8"))


def _check_path(path: Path) -> None:
    # The path is put inside SQL strings, so a quote could break out of them.
    if "'" in str(path):
        raise TransformError(f"data folder path must not contain a quote: {path}")
