"""Example CVs with the answers they should get, to show and to test the CV analysis.

Each example is a folder in showcase/cv:

    cv.md         the CV text (a fictional person)
    case.yaml     who it is, the role and region to compare with, and checks: what a
                  person reading the CV expects, each with the reason
    profile.json  Claude's reading of the CV, saved by `skillradar-cv showcase --refresh`

Profile checks test the reading (role, seniority, languages, skills). They use the saved
profile, so they run in the tests without the API. Match checks test the comparison with
today's postings; they need the data and run in `skillradar-cv showcase`, which writes
showcase/cv/REPORT.md.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from skillradar.config import PROJECT_ROOT
from skillradar.cv.profile import CvProfile, language_levels
from skillradar.skills.taxonomy import key

SHOWCASE_DIR = PROJECT_ROOT / "showcase" / "cv"
CASE_ID = re.compile(r"[a-z0-9][a-z0-9-]{1,40}")

PROFILE_KINDS = ("role", "seniority", "years", "language", "has", "lacks", "evidence")
MATCH_KINDS = ("best_role", "covered", "gap", "no_gap", "good_share")


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Check(_Closed):
    kind: Literal[
        "role", "seniority", "years", "language", "has", "lacks", "evidence",
        "best_role", "covered", "gap", "no_gap", "good_share",
    ]  # fmt: skip
    why: str = Field(min_length=10)
    values: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    skill: str | None = None
    language: str | None = None
    via: str | None = None
    min: float | None = None
    max: float | None = None
    top: int = 3


class Target(_Closed):
    role: str
    region: str


class CaseFile(_Closed):
    title: str
    person: str
    language: Literal["English", "German"]
    target: Target
    story: str
    checks: list[Check] = Field(min_length=1)


@dataclass
class Result:
    check: Check
    passed: bool
    actual: str


@dataclass
class Case:
    id: str
    file: CaseFile
    text: str
    profile: CvProfile | None
    saved: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "title": self.file.title,
            "person": self.file.person,
            "language": self.file.language,
            "target": self.file.target.model_dump(),
        }

    def detail(self) -> dict:
        return {
            **self.summary(),
            "story": self.file.story,
            "text": self.text,
            "profile": self.profile.model_dump() if self.profile else None,
            "notes": self.saved.get("notes", []),
            "read": {k: self.saved.get(k) for k in ("read_at", "model", "prompt_version")},
            "checks": [c.model_dump(exclude_defaults=True) for c in self.file.checks],
        }


def load(folder: Path, case_id: str) -> Case | None:
    if not CASE_ID.fullmatch(case_id):
        return None
    path = folder / case_id
    if not (path / "case.yaml").is_file() or not (path / "cv.md").is_file():
        return None
    with (path / "case.yaml").open(encoding="utf-8") as f:
        file = CaseFile.model_validate(yaml.safe_load(f))
    saved: dict[str, Any] = {}
    profile = None
    if (path / "profile.json").is_file():
        # A profile saved by an older version may not fit; it is read again on --refresh.
        try:
            saved = json.loads((path / "profile.json").read_text(encoding="utf-8"))
            profile = CvProfile.model_validate(saved["profile"])
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError):
            saved, profile = {"invalid": True}, None
    return Case(case_id, file, (path / "cv.md").read_text(encoding="utf-8"), profile, saved)


def load_all(folder: Path) -> list[Case]:
    if not folder.is_dir():
        return []
    cases = [load(folder, p.name) for p in sorted(folder.iterdir()) if p.is_dir()]
    return [c for c in cases if c is not None]


def save_profile(folder: Path, case_id: str, record: dict[str, Any]) -> None:
    path = folder / case_id / "profile.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def check_profile(case: Case) -> list[Result]:
    profile = case.profile
    checks = [c for c in case.file.checks if c.kind in PROFILE_KINDS]
    if profile is None:
        return [Result(c, False, "no saved profile") for c in checks]
    skills = {key(s.name): s for s in profile.skills}
    levels = language_levels(profile)
    results = []
    for c in checks:
        if c.kind == "role":
            results.append(Result(c, profile.role in c.values, profile.role))
        elif c.kind == "seniority":
            results.append(Result(c, profile.seniority in c.values, profile.seniority))
        elif c.kind == "years":
            years = profile.years_experience
            ok = years is not None and _between(years, c.min, c.max)
            results.append(Result(c, ok, "unknown" if years is None else f"{years:g}"))
        elif c.kind == "language":
            level = levels.get(c.language or "")
            results.append(Result(c, level in c.values, level or "not found"))
        elif c.kind == "has":
            missing = [s for s in c.skills if key(s) not in skills]
            actual = f"missing: {', '.join(missing)}" if missing else "all found"
            results.append(Result(c, not missing, actual))
        elif c.kind == "lacks":
            found = [s for s in c.skills if key(s) in skills]
            actual = f"found: {', '.join(found)}" if found else "none found"
            results.append(Result(c, not found, actual))
        elif c.kind == "evidence":
            skill = skills.get(key(c.skill or ""))
            actual = skill.evidence if skill else "not found"
            results.append(Result(c, actual in c.values, actual))
    return results


def check_match(case: Case, analysis: dict) -> list[Result]:
    results = []
    gap_names = [g["name"] for g in analysis["gaps"]]
    demand = {key(d["skill"]): d for d in analysis["demand"]}
    for c in (c for c in case.file.checks if c.kind in MATCH_KINDS):
        if c.kind == "best_role":
            ranked = [r["id"] for r in analysis["roles"]]
            top = ranked[: c.top]
            ok = any(v in top for v in c.values)
            results.append(Result(c, ok, f"top {c.top}: {', '.join(top) or 'none'}"))
        elif c.kind == "covered":
            row = demand.get(key(c.skill or ""))
            if row is None:
                results.append(Result(c, False, "not among the most asked skills"))
                continue
            coverage = row["coverage"]
            ok = coverage["kind"] in c.values and (c.via is None or coverage["via"] == c.via)
            actual = coverage["kind"] + (f" via {coverage['via']}" if coverage["via"] else "")
            results.append(Result(c, ok, actual))
        elif c.kind == "gap":
            top = gap_names[: c.top]
            wanted = c.skills or [c.skill or ""]
            ok = any(w in top for w in wanted)
            results.append(Result(c, ok, f"top {c.top} gaps: {', '.join(top) or 'none'}"))
        elif c.kind == "no_gap":
            ok = c.skill not in gap_names
            results.append(Result(c, ok, "not a gap" if ok else "listed as a gap"))
        elif c.kind == "good_share":
            good = analysis["summary"]["good_or_better"]
            scored = analysis["summary"]["scored"]
            share = good / scored if scored else 0.0
            ok = scored > 0 and _between(share, c.min, c.max)
            results.append(Result(c, ok, f"{good} of {scored} postings ({share:.0%})"))
    return results


def _between(value: float, low: float | None, high: float | None) -> bool:
    return (low is None or value >= low) and (high is None or value <= high)


def report(entries: list[tuple[Case, list[Result], dict | None]], as_of: str | None) -> str:
    """Markdown: per example, what was expected, what came out, and why it should."""
    total = sum(len(results) for _, results, _ in entries)
    passed = sum(r.passed for _, results, _ in entries for r in results)
    lines = [
        "# CV analysis: showcase report",
        "",
        "Written by `uv run skillradar-cv showcase`. Every check says what a person reading",
        "the CV expects and why; ✅ means the analysis agrees, ❌ means it does not.",
        "Profile checks test how the CV was read; match checks compare it with the open",
        f"postings as of {as_of or 'unknown'}, so they can change as the postings change.",
        "",
        f"**{passed} of {total} checks pass.**",
        "",
        "| Example | Target | Checks |",
        "|---|---|---|",
    ]
    for case, results, _ in entries:
        ok = sum(r.passed for r in results)
        target = f"{case.file.target.role}, {case.file.target.region}"
        lines.append(f"| [{case.file.title}](#{case.id}) | {target} | {ok} / {len(results)} |")
    for case, results, analysis in entries:
        lines += ["", f"## {case.file.title}", "", f'<a id="{case.id}"></a>', ""]
        lines += [f"*{case.file.person}*, CV in {case.file.language}. {case.file.story.strip()}"]
        if analysis:
            s = analysis["summary"]
            lines += [
                "",
                f"Compared with {s['scored']} postings ({analysis['role_label']}, "
                f"{analysis['region_label']}): {s['good_or_better']} at least a good match.",
            ]
            gaps = ", ".join(f"{g['name']} (+{g['gained']})" for g in analysis["gaps"][:5])
            if gaps:
                lines.append(f"Top gaps: {gaps}.")
        lines += ["", "| | Check | Why | Result |", "|---|---|---|---|"]
        for r in results:
            mark = "✅" if r.passed else "❌"
            lines.append(f"| {mark} | {describe(r.check)} | {r.check.why} | {r.actual} |")
    return "\n".join(lines) + "\n"


def describe(c: Check) -> str:
    match c.kind:
        case "role" | "seniority":
            return f"{c.kind} is {' or '.join(c.values)}"
        case "years":
            return f"years of experience {c.min:g} to {c.max:g}"
        case "language":
            return f"{c.language} is {' or '.join(c.values)}"
        case "has":
            return f"finds {', '.join(c.skills)}"
        case "lacks":
            return f"does not invent {', '.join(c.skills)}"
        case "evidence":
            return f"{c.skill} counted as {' or '.join(c.values)}"
        case "best_role":
            return f"{' or '.join(c.values)} in the top {c.top} roles"
        case "covered":
            via = f" via {c.via}" if c.via else ""
            return f"{c.skill} covered as {' or '.join(c.values)}{via}"
        case "gap":
            return f"{' or '.join(c.skills or [c.skill or ''])} in the top {c.top} gaps"
        case "no_gap":
            return f"{c.skill} is not a gap"
        case _:
            low = "" if c.min is None else f"at least {c.min:.0%}"
            high = "" if c.max is None else f"at most {c.max:.0%}"
            return f"share of good matches {' and '.join(x for x in (low, high) if x)}"


def validate_all(folder: Path) -> list[str]:
    """Problems with the example files, for the tests."""
    problems = []
    for path in sorted(p for p in folder.iterdir() if p.is_dir()):
        try:
            case = load(folder, path.name)
        except (ValidationError, yaml.YAMLError, json.JSONDecodeError, KeyError) as error:
            problems.append(f"{path.name}: {error}")
            continue
        if case is None:
            problems.append(f"{path.name}: needs cv.md and case.yaml")
        elif case.saved.get("invalid"):
            problems.append(f"{path.name}: profile.json does not fit; run showcase --refresh")
    return problems
