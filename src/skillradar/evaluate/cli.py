"""Command line: uv run skillradar-eval sample|status|texts|drafts|report

All commands are free: nothing is sent to Claude.

sample   draw the postings to label (eval/labels.jsonl)
status   how many are todo, draft and verified
texts    write the sample's texts to data/eval/texts.jsonl (the review page reads it)
drafts   save draft labels from a JSON lines file ({"refnr": ..., "answer": {...}})
report   compare keywords and Claude with the verified labels (data/eval/report.json)
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from skillradar.api.postings import readable
from skillradar.config import DATA_DIR
from skillradar.evaluate.labels import (
    LABELS_PATH,
    Answer,
    LabelError,
    LabelStore,
    draw_sample,
    texts_path,
    utc_now,
)
from skillradar.evaluate.report import build_report
from skillradar.extract.postings import load_postings
from skillradar.extract.prompt import PROMPT_VERSION
from skillradar.extract.settings import load_settings
from skillradar.extract.store import ExtractionStore
from skillradar.extract.tables import current_answers
from skillradar.skills.taxonomy import load_taxonomy
from skillradar.storage import atomic_write, json_line, read_json_lines
from skillradar.transform.runner import warehouse_path

DEFAULT_SIZE = 150
DEFAULT_SEED = 20261107


def report_path(data_dir: Path) -> Path:
    return data_dir / "eval" / "report.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure the extraction against labels.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--labels", type=Path, default=LABELS_PATH)
    commands = parser.add_subparsers(dest="command", required=True)
    sample = commands.add_parser("sample", help="draw the postings to label")
    sample.add_argument("--size", type=int, default=DEFAULT_SIZE)
    sample.add_argument("--seed", type=int, default=DEFAULT_SEED)
    commands.add_parser("status", help="labels per status")
    texts = commands.add_parser("texts", help="write the sample's texts for the review page")
    texts.add_argument("--out", type=Path, help="another file, e.g. for writing drafts")
    texts.add_argument("--todo", action="store_true", help="only postings without a label")
    drafts = commands.add_parser("drafts", help="save draft labels from a file")
    drafts.add_argument("file", type=Path)
    drafts.add_argument("--by", required=True, help="who wrote the drafts, e.g. a model name")
    report = commands.add_parser("report", help="score keywords and Claude")
    report.add_argument(
        "--drafts", action="store_true", help="also use unchecked drafts (marked as such)"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    store = LabelStore(args.labels)
    try:
        if args.command == "sample":
            return _sample(store, args)
        if args.command == "status":
            return _status(store)
        if args.command == "texts":
            return _texts(store, args)
        if args.command == "drafts":
            return _drafts(store, args)
        return _report(store, args)
    except (LabelError, ValidationError, FileNotFoundError) as error:
        print(error, file=sys.stderr)
        return 1


def _sample(store: LabelStore, args: argparse.Namespace) -> int:
    # Only postings Claude answered with the current prompt: those are what the site shows.
    texts = _texts_by_refnr(args.data_dir)
    answered = {a["refnr"] for a in _current(args.data_dir)} & set(texts)
    refnrs = draw_sample(answered, args.size, args.seed)
    store.create(refnrs)
    print(f"sample of {len(refnrs)} from {len(answered)} postings (seed {args.seed})")
    print(f"written to {store.path}")
    _write_texts(store, texts, texts_path(args.data_dir), todo_only=False)
    return 0


def _status(store: LabelStore) -> int:
    counts = Counter(label.status for label in store.load())
    total = sum(counts.values())
    verified, draft, todo = counts["verified"], counts["draft"], counts["todo"]
    print(f"{total} postings: {verified} verified, {draft} draft, {todo} todo")
    return 0


def _texts(store: LabelStore, args: argparse.Namespace) -> int:
    out = args.out or texts_path(args.data_dir)
    _write_texts(store, _texts_by_refnr(args.data_dir), out, todo_only=args.todo)
    return 0


def _write_texts(store: LabelStore, texts: dict, out: Path, todo_only: bool) -> None:
    """Title and readable text per posting; never Claude's answer, so it can't sway a label."""
    refnrs = [x.refnr for x in store.load() if x.status == "todo" or not todo_only]
    lines = [
        json_line({"refnr": r, "title": texts[r].title, "text": readable(texts[r].description)})
        for r in refnrs
        if r in texts
    ]
    atomic_write(out, "".join(lines).encode("utf-8"))  # private: the posting texts
    print(f"{len(lines)} texts written to {out}")


def _drafts(store: LabelStore, args: argparse.Namespace) -> int:
    drafts = {}
    for record in read_json_lines(args.file):
        drafts[str(record.get("refnr"))] = Answer.model_validate(record.get("answer"))
    saved = store.add_drafts(drafts, by=args.by)
    print(f"{saved} drafts saved ({len(drafts) - saved} skipped: not todo)")
    return 0


def _report(store: LabelStore, args: argparse.Namespace) -> int:
    statuses = {"verified", "draft"} if args.drafts else {"verified"}
    all_labels = store.load()
    labels = [label for label in all_labels if label.status in statuses]
    if not labels:
        print("no labels to score yet; verify some on the review page first", file=sys.stderr)
        return 1
    settings = load_settings()
    report = build_report(
        labels,
        _texts_by_refnr(args.data_dir),
        ExtractionStore(args.data_dir / "llm").results(),
        load_taxonomy(),
        settings.model,
        PROMPT_VERSION,
    )
    counts = Counter(label.status for label in all_labels)
    sample = {"size": len(all_labels)} | {s: counts[s] for s in ("todo", "draft", "verified")}
    report = {
        "generated_at": utc_now(),
        "includes_drafts": args.drafts,
        "sample": sample,
        **report,
    }
    path = report_path(args.data_dir)
    atomic_write(path, json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
    _print_report(report)
    print(f"\nwritten to {path}")
    return 0


def _print_report(report: dict) -> None:
    if report["includes_drafts"]:
        print("UNCHECKED: these numbers include drafts that nobody verified yet.\n")
    print(f"{report['labels']} labeled postings")
    for key, title in (
        ("skills", "Skills in the skill list (main number)"),
        ("all_skills", "All skills (lower bound: other names must match exactly)"),
    ):
        print(f"\n{title}")
        print(f"{'system':58} {'n':>4} {'precision':>16} {'recall':>16} {'F1':>16}")
        for system in report["systems"]:
            scores = system[key]
            if not scores:
                continue
            print(
                f"{system['name'][:58]:58} {system['postings']:>4} "
                f"{_cell(scores['precision'])} {_cell(scores['recall'])} {_cell(scores['f1'])}"
            )
    main = next(s for s in report["systems"] if s["id"].endswith("/counted"))
    print("\nClaude, as counted on the site:")
    for name in ("role", "seniority", "remote"):
        print(f"  {name:12} accuracy {_cell(main[name]['accuracy'])}  n={main[name]['n']}")
    required = main["required"]
    print(f"  {'required':12} accuracy {_cell(required['accuracy'])}  n={required['n']}")
    listed = [row for row in report["skills"] if row["in_skill_list"] and row["recall"] is not None]
    worst = sorted(listed, key=lambda row: (row["recall"], -row["labeled"]))[:5]
    if worst:
        missed = ", ".join(f"{row['skill']} ({row['fn']} of {row['labeled']})" for row in worst)
        print(f"\nlisted skills missed most often: {missed}")


def _cell(score: dict) -> str:
    if score["value"] is None:
        return f"{'-':>16}"
    interval = f"({score['low']:.2f}-{score['high']:.2f})" if score["low"] is not None else ""
    return f"{score['value']:.2f} {interval:>11}"


def _texts_by_refnr(data_dir: Path):
    warehouse = warehouse_path(data_dir)
    if not warehouse.exists():
        raise FileNotFoundError(f"no warehouse at {warehouse}; run skillradar-transform first")
    return {posting.refnr: posting for posting in load_postings(warehouse)}


def _current(data_dir: Path):
    results = ExtractionStore(data_dir / "llm").results()
    return current_answers(results, load_settings().model, PROMPT_VERSION)


if __name__ == "__main__":
    raise SystemExit(main())
