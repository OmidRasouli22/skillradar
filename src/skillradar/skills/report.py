"""Command line: uv run skillradar-skills report [--title TEXT] [--top N]

Keyword search over the cleaned descriptions. Shows how often each skill appears.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

import duckdb

from skillradar.config import DATA_DIR
from skillradar.skills.taxonomy import Taxonomy, load_taxonomy
from skillradar.transform.runner import warehouse_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Skill counts from a keyword search.")
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("report", help="most common skills in the postings")
    report.add_argument("--data-dir", type=Path, default=DATA_DIR)
    report.add_argument("--title", help="only postings whose title contains this text")
    report.add_argument("--top", type=int, default=25)
    return parser.parse_args(argv)


def load_texts(warehouse: Path, title: str | None) -> list[str]:
    sql = """
        select t.description
        from silver_posting_texts t
        join silver_postings p using (refnr)
        where ? is null or p.title ilike '%' || ? || '%'
    """
    with duckdb.connect(str(warehouse), read_only=True) as con:
        return [text for (text,) in con.execute(sql, [title, title]).fetchall()]


def count_skills(texts: list[str], taxonomy: Taxonomy) -> Counter[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        counts.update(taxonomy.find_in_text(text))
    return counts


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    warehouse = warehouse_path(args.data_dir.resolve())
    if not warehouse.exists():
        print(f"{warehouse} not found, run skillradar-transform first", file=sys.stderr)
        return 1

    taxonomy = load_taxonomy()
    texts = load_texts(warehouse, args.title)
    if not texts:
        print("no postings match", file=sys.stderr)
        return 1

    counts = count_skills(texts, taxonomy)
    with_skill = sum(1 for text in texts if taxonomy.find_in_text(text))
    print(f"{len(texts)} postings, {with_skill / len(texts):.0%} with at least one known skill\n")
    for name, count in counts.most_common(args.top):
        share = count / len(texts)
        print(
            f"{name:<24} {taxonomy.category_of(name):<13} {share:6.1%}  {'#' * round(share * 40)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
