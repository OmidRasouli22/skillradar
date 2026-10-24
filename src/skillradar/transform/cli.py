"""Command line: uv run skillradar-transform [--select MODEL]"""

import argparse
import os
import sys
from pathlib import Path

from skillradar.config import DATA_DIR
from skillradar.transform.runner import TransformError, build, warehouse_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build silver tables from bronze.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--select", help="only these dbt models, e.g. silver_postings")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    os.umask(0o077)  # the warehouse holds personal data, keep new files private
    try:
        build(args.data_dir, select=args.select)
    except TransformError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"done: {warehouse_path(args.data_dir.resolve())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
