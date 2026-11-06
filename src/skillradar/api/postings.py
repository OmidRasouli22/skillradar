"""The job list and the job view: one posting with the important parts marked.

Marks come in four kinds: a required skill, a nice-to-have skill, a language the posting
asks for, and home office. Skills are found with the same rules that decide if a posting
names a skill, so the page marks exactly what was counted.
"""

import html
import re

from skillradar.skills.matching import prepare, spans
from skillradar.skills.taxonomy import Taxonomy

# Reference numbers from the job search, e.g. "13635-f28d5696_JB5265243-S".
REFNR = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,79}")
JOB_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"

# "Deutschkenntnisse", "fließend Englisch", "English"; not the country ("Deutschland").
LANGUAGE = re.compile(r"\b(?:Deutsch(?!land)|Englisch|German(?!y)|English)\w*", re.IGNORECASE)
HOME_OFFICE = re.compile(
    r"\b(?:Home[\s-]?Office|Homeoffice|Remote|Hybrid\w*|mobile[ns]?\s+Arbeiten|Telearbeit)\b",
    re.IGNORECASE,
)


def readable(text: str) -> str:
    """The posting text without Markdown signs and HTML entities, for reading.

    Postings often contain "### Heading", "**bold**" and "&nbsp;". The page shows plain
    text (never HTML), so these signs are removed. Marks are found in this text.
    """
    text = html.unescape(text).replace("\u00a0", " ")
    text = re.sub(r"^[ \t]*#{1,6}[ \t]+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*|__", "", text)
    text = re.sub(r"^[ \t]*[*•][ \t]+", "- ", text, flags=re.MULTILINE)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def marks(text: str, skills: list[tuple[str, bool]], taxonomy: Taxonomy) -> list[dict]:
    """Where to mark the text: skills first, then languages and home office.

    Marks never overlap: when two would, the earlier and then the longer one wins.
    """
    prepared = prepare(text)
    found: list[tuple[int, int, str, str]] = []
    for skill, required in skills:
        kind = "required" if required else "nice"
        for term in taxonomy.spellings_of(skill) or [skill]:
            found += [(start, end, kind, skill) for start, end in spans(prepared, term)]
    for kind, pattern in (("language", LANGUAGE), ("home_office", HOME_OFFICE)):
        found += [(m.start(), m.end(), kind, m.group(0)) for m in pattern.finditer(prepared)]

    chosen: list[tuple[int, int, str, str]] = []
    for start, end, kind, label in sorted(found, key=lambda m: (m[0], -(m[1] - m[0]))):
        if chosen and start < chosen[-1][1]:
            continue
        chosen.append((start, end, kind, label))
    return [{"start": s, "end": e, "kind": k, "label": label} for s, e, k, label in chosen]
