"""Quality numbers for saved answers, one block per model and prompt version. Free.

Used to compare prompt versions and to spot problems before a large run.
"""

from collections import Counter, defaultdict
from statistics import median

from skillradar.skills.taxonomy import Taxonomy
from skillradar.storage import Record


def summary(results: list[Record], taxonomy: Taxonomy) -> dict[tuple[str, str], dict]:
    groups: dict[tuple[str, str], list[Record]] = defaultdict(list)
    for record in results:
        groups[(record["model"], record["prompt_version"])].append(record)
    return {group: _numbers(records, taxonomy) for group, records in sorted(groups.items())}


def _numbers(records: list[Record], taxonomy: Taxonomy) -> dict:
    answers = [r["output"] for r in records if r["status"] == "ok"]
    skills = [s for a in answers for s in a["skills"]]
    known = sum(taxonomy.normalize(s["name"]) is not None for s in skills)
    return {
        "answers": len(records),
        "status": dict(Counter(r["status"] for r in records)),
        "seniority unknown": _share(a["seniority"] == "unknown" for a in answers),
        "remote unknown": _share(a["remote"] == "unknown" for a in answers),
        "no skills": _share(not a["skills"] for a in answers),
        "skills per answer": median(len(a["skills"]) for a in answers) if answers else 0,
        "skills required": _share(s["required"] for s in skills),
        "skills in skill list": round(known / len(skills), 2) if skills else 0,
        "languages": dict(Counter(x["language"] for a in answers for x in a["languages"])),
        "max output tokens": max((r["usage"]["output_tokens"] for r in records), default=0),
    }


def _share(flags) -> float:
    flags = list(flags)
    return round(sum(flags) / len(flags), 2) if flags else 0
