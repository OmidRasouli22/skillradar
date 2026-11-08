"""skillradar-cv: read a CV, compare it with the postings, run the showcase examples.

    uv run skillradar-cv read my_cv.pdf [--keywords] [--out profile.json]
    uv run skillradar-cv match profile.json --role data_engineer --region BERLIN
    uv run skillradar-cv showcase [--refresh] [--only ID]

read with Claude and showcase --refresh cost money (about $0.002 per CV with Haiku),
within the monthly limit in config/llm.yaml. Everything else is free.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from skillradar.api.labels import REGIONS, ROLES
from skillradar.config import DATA_DIR, PROJECT_ROOT
from skillradar.cv import showcase
from skillradar.cv.families import load_families
from skillradar.cv.market import NoMarket, load_market
from skillradar.cv.match import analyse
from skillradar.cv.profile import CvProfile
from skillradar.cv.reader import (
    CV_PROMPT_VERSION,
    CvError,
    make_client,
    pdf_text,
    read_with_claude,
    read_with_keywords,
)
from skillradar.extract import budget
from skillradar.extract.settings import load_settings
from skillradar.extract.store import ExtractionStore
from skillradar.skills.taxonomy import load_taxonomy
from skillradar.transform.runner import serve_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skillradar-cv", description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    commands = parser.add_subparsers(dest="command", required=True)

    read = commands.add_parser("read", help="read a CV (.pdf, .md or .txt) into a profile")
    read.add_argument("path", type=Path)
    read.add_argument("--keywords", action="store_true", help="free keyword read, no Claude")
    read.add_argument("--out", type=Path, help="save the profile as JSON")

    match = commands.add_parser("match", help="compare a saved profile with the postings")
    match.add_argument("profile", type=Path)
    match.add_argument("--role", default="all", choices=sorted(ROLES))
    match.add_argument("--region", default="all", choices=sorted(REGIONS))

    cases = commands.add_parser("showcase", help="check the example CVs, write the report")
    cases.add_argument("--refresh", action="store_true", help="read the CVs with Claude again")
    cases.add_argument(
        "--stale", action="store_true", help="read only CVs saved with an older prompt"
    )
    cases.add_argument("--only", help="one example id")
    cases.add_argument("--folder", type=Path, default=showcase.SHOWCASE_DIR)

    args = parser.parse_args(argv)
    try:
        if args.command == "read":
            return _read(args)
        if args.command == "match":
            return _match(args)
        return _showcase(args)
    except (CvError, NoMarket, budget.OverBudget, anthropic.APIError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _read(args: argparse.Namespace) -> int:
    taxonomy = load_taxonomy()
    data = args.path.read_bytes()
    text = pdf_text(data)[0] if args.path.suffix.lower() == ".pdf" else data.decode("utf-8")
    if args.keywords:
        result = read_with_keywords(text, taxonomy)
    else:
        result = read_with_claude(
            _client(), text, load_settings(), taxonomy, ExtractionStore(args.data_dir / "llm")
        )
    record = {
        "notes": result.notes,
        "cost_usd": result.cost_usd,
        "profile": result.profile.model_dump(),
    }
    output = json.dumps(record, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(output + "\n", encoding="utf-8")
        print(f"saved {args.out} (cost ${result.cost_usd:.4f})")
    else:
        print(output)
    return 0


def _match(args: argparse.Namespace) -> int:
    saved = json.loads(args.profile.read_text(encoding="utf-8"))
    profile = CvProfile.model_validate(saved.get("profile", saved))
    taxonomy = load_taxonomy()
    market = load_market(serve_dir(args.data_dir), taxonomy)
    families = load_families(taxonomy)
    result = analyse(profile, market, families, args.role, args.region, _year(), taxonomy)
    s = result["summary"]
    print(f"{result['role_label']}, {result['region_label']} (postings as of {result['as_of']})")
    print(f"{s['scored']} postings compared, {s['good_or_better']} at least a good match")
    print("best roles:", ", ".join(f"{r['label']} {r['share']:.0%}" for r in result["roles"][:5]))
    print("learn next:")
    for gap in result["gaps"][:10]:
        print(f"  {gap['name']:<28} +{gap['gained']} good matches, asked in {gap['postings']}")
    return 0


def _showcase(args: argparse.Namespace) -> int:
    taxonomy = load_taxonomy()
    folder = args.folder
    cases = showcase.load_all(folder)
    if args.only:
        cases = [c for c in cases if c.id == args.only]
        if not cases:
            print(f"error: no example {args.only}", file=sys.stderr)
            return 1
    if args.refresh or args.stale:
        client, settings = _client(), load_settings()
        store = ExtractionStore(args.data_dir / "llm")
        for case in cases:
            if args.stale and case.saved.get("prompt_version") == CV_PROMPT_VERSION:
                continue
            # One failed read must not stop the others; its old reading stays.
            try:
                result = read_with_claude(client, case.text, settings, taxonomy, store)
            except (CvError, anthropic.APIError) as error:
                print(f"could not read {case.id}: {error}", file=sys.stderr)
                continue
            showcase.save_profile(
                folder,
                case.id,
                {
                    "read_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "model": settings.model,
                    "prompt_version": CV_PROMPT_VERSION,
                    "cost_usd": result.cost_usd,
                    "notes": result.notes,
                    "profile": result.profile.model_dump(),
                },
            )
            print(f"read {case.id} (${result.cost_usd:.4f})")
        cases = [showcase.load(folder, c.id) for c in cases]

    try:
        market = load_market(serve_dir(args.data_dir), taxonomy)
    except NoMarket:
        market = None
        print("no postings data: only the profile checks run")
    families = load_families(taxonomy)
    entries = []
    for case in cases:
        results = showcase.check_profile(case)
        analysis = None
        if market is not None and case.profile is not None:
            target = case.file.target
            analysis = analyse(
                case.profile, market, families, target.role, target.region, _year(), taxonomy
            )
            results += showcase.check_match(case, analysis)
        entries.append((case, results, analysis))
        ok = sum(r.passed for r in results)
        print(f"{case.id:<28} {ok} / {len(results)} checks pass")
        for r in results:
            if not r.passed:
                print(f"   ❌ {r.check.kind}: {r.actual} ({r.check.why})")
    if not args.only:
        path = folder / "REPORT.md"
        path.write_text(
            showcase.report(entries, market.as_of if market else None), encoding="utf-8"
        )
        print(
            f"wrote {path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path}"
        )
    return 0


def _client() -> anthropic.Anthropic:
    load_dotenv(PROJECT_ROOT / ".env")
    return make_client()


def _year() -> int:
    return datetime.now(UTC).year


if __name__ == "__main__":
    raise SystemExit(main())
