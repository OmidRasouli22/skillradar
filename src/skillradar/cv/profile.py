"""A CV as structured data, built like a posting's answer so the two can be compared.

CvAnswer is what Claude returns. It is checked loosely: one odd number must not throw
away a whole CV, so numbers out of range become null. CvProfile is the cleaned result,
which the page shows, the person can edit, and the matching reads. It is checked strictly.

Two things are left to code, not to Claude, because a language model gets them wrong:
years of experience are counted from the jobs' dates (overlaps once), and language names
are mapped to the fixed list here (a fixed list in the answer derails Claude when the
person's language is not on it).
"""

import re
from datetime import date
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from skillradar.extract.schema import (
    Language,
    LanguageRequirement,
    Level,
    Role,
    Seniority,
    Strict,
    enum_schema,
    object_schema,
)
from skillradar.skills.taxonomy import key

Evidence = Literal["work", "project", "education", "listed"]
JobKind = Literal[
    "job", "freelance", "working_student", "internship", "apprenticeship", "thesis", "other"
]
# Only these count as professional experience, and only for tech work.
COUNTED_JOBS = ("job", "freelance")
# A CV is compared with tech jobs, so its role is the closest tech role.
CvRole = Literal[tuple(r for r in get_args(Role) if r != "not_tech")]  # type: ignore[valid-type]
Source = Literal["claude", "keyword", "you"]

# How much a skill counts, by the strongest place the CV shows it. A recruiter trusts a
# skill used in a job more than one only named in a skills list.
EVIDENCE_STRENGTH: dict[str, float] = {
    "work": 1.0,
    "project": 0.8,
    "education": 0.7,
    "listed": 0.6,
}
EVIDENCE_ORDER = ("work", "project", "education", "listed")
# A skill last used this many years ago or longer counts a little less.
STALE_YEARS = 5
STALE_FACTOR = 0.8

MAX_YEARS = 60
FIRST_YEAR = 1970
MAX_SKILLS = 150


def _nullable(kind: str) -> dict:
    return {"anyOf": [{"type": kind}, {"type": "null"}]}


CV_SCHEMA = object_schema(
    {
        "headline": {"type": "string"},
        "role": enum_schema(CvRole),
        "seniority": enum_schema(Seniority),
        "jobs": {
            "type": "array",
            "items": object_schema(
                {
                    "title": {"type": "string"},
                    "start": _nullable("string"),
                    "end": _nullable("string"),
                    "kind": enum_schema(JobKind),
                    "tech": {"type": "boolean"},
                }
            ),
        },
        "languages": {
            "type": "array",
            "items": object_schema({"language": {"type": "string"}, "level": enum_schema(Level)}),
        },
        "skills": {
            "type": "array",
            "items": object_schema(
                {
                    "name": {"type": "string"},
                    "evidence": enum_schema(Evidence),
                    "years": _nullable("number"),
                    "last_used": _nullable("integer"),
                    "context": {"type": "string"},
                }
            ),
        },
    }
)


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


class AnswerSkill(_Loose):
    name: str
    evidence: Evidence
    years: float | None = None
    last_used: int | None = None
    context: str = ""


class AnswerJob(_Loose):
    title: str = ""
    start: str | None = None
    end: str | None = None
    kind: JobKind
    tech: bool


class AnswerLanguage(_Loose):
    language: str
    level: Level


class CvAnswer(_Loose):
    headline: str = ""
    role: CvRole
    seniority: Seniority
    jobs: list[AnswerJob] = Field(default_factory=list)
    languages: list[AnswerLanguage] = Field(default_factory=list)
    skills: list[AnswerSkill] = Field(default_factory=list)


class CvSkill(Strict):
    name: str = Field(min_length=1, max_length=80)
    evidence: Evidence
    years: float | None = Field(default=None, ge=0, le=MAX_YEARS)
    last_used: int | None = Field(default=None, ge=FIRST_YEAR, le=2100)
    context: str = Field(default="", max_length=160)
    source: Source = "you"


class CvProfile(Strict):
    headline: str = Field(default="", max_length=120)
    role: CvRole
    seniority: Seniority
    years_experience: float | None = Field(default=None, ge=0, le=MAX_YEARS)
    languages: list[LanguageRequirement] = Field(default_factory=list, max_length=20)
    skills: list[CvSkill] = Field(default_factory=list, max_length=MAX_SKILLS)


def strength(skill: CvSkill, this_year: int) -> float:
    """How much a skill counts, from 0.48 (only listed, long ago) to 1.0 (used at work)."""
    value = EVIDENCE_STRENGTH[skill.evidence]
    if skill.last_used is not None and this_year - skill.last_used >= STALE_YEARS:
        value *= STALE_FACTOR
    return value


def merge_skills(skills: list[CvSkill]) -> list[CvSkill]:
    """One entry per skill name: the strongest evidence, the most years, the latest use."""
    merged: dict[str, CvSkill] = {}
    for skill in skills:
        k = key(skill.name)
        old = merged.get(k)
        if old is None:
            merged[k] = skill
            continue
        stronger = min(old, skill, key=lambda s: EVIDENCE_ORDER.index(s.evidence))
        merged[k] = stronger.model_copy(
            update={
                "years": _max(old.years, skill.years),
                "last_used": _max(old.last_used, skill.last_used),
            }
        )
    return list(merged.values())


def _max(a, b):
    values = [v for v in (a, b) if v is not None]
    return max(values) if values else None


def language_levels(profile: CvProfile) -> dict[str, str]:
    """The level per language; a language named twice keeps its higher level."""
    order = ("unknown", "basic", "good", "fluent", "native")
    levels: dict[str, str] = {}
    for item in profile.languages:
        old = levels.get(item.language)
        if old is None or order.index(item.level) > order.index(old):
            levels[item.language] = item.level
    return levels


MONTH = re.compile(r"\s*(\d{4})(?:\s*[-/.]\s*(\d{1,2}))?\s*")
PRESENT = {"present", "heute", "now", "today", "current", "aktuell", "bis heute", "ongoing"}


def experience_years(jobs: list[AnswerJob], today: date) -> float | None:
    """Years of tech jobs and freelance work, from the dates; overlapping months count once.
    None when no counted job has a start date."""
    months: set[int] = set()
    dated = False
    for job in jobs:
        start = _month(job.start, today, end=False)
        if start is None:
            continue
        dated = True
        if job.kind not in COUNTED_JOBS or not job.tech:
            continue
        end = _month(job.end, today, end=True)
        if end is None or end < start:
            continue
        months.update(range(start, min(end, _index(today.year, today.month)) + 1))
    if not dated:
        return None
    return round(len(months) / 12, 1)


def _month(text: str | None, today: date, end: bool) -> int | None:
    """A month as a number (year * 12 + month); a year alone is January or December."""
    if text is None:
        return None
    if text.strip().casefold() in PRESENT:
        return _index(today.year, today.month) if end else None
    found = MONTH.fullmatch(text)
    if not found:
        return None
    year = int(found.group(1))
    month = int(found.group(2)) if found.group(2) else (12 if end else 1)
    if not FIRST_YEAR <= year <= today.year or not 1 <= month <= 12:
        return None
    return _index(year, month)


def _index(year: int, month: int) -> int:
    return year * 12 + month - 1


LANGUAGE_NAMES = {
    "deutsch": "German", "englisch": "English", "französisch": "French",
    "franzosisch": "French", "spanisch": "Spanish", "italienisch": "Italian",
    "niederländisch": "Dutch", "niederlandisch": "Dutch", "holländisch": "Dutch",
    "polnisch": "Polish", "portugiesisch": "Portuguese", "tschechisch": "Czech",
    "russisch": "Russian", "ukrainisch": "Ukrainian", "türkisch": "Turkish",
    "turkisch": "Turkish", "arabisch": "Arabic", "chinesisch": "Chinese", "mandarin": "Chinese",
    "japanisch": "Japanese", "koreanisch": "Korean", "schwedisch": "Swedish",
    "dänisch": "Danish", "danisch": "Danish", "norwegisch": "Norwegian", "finnisch": "Finnish",
    "ungarisch": "Hungarian", "rumänisch": "Romanian", "rumanisch": "Romanian",
    "griechisch": "Greek",
}  # fmt: skip


def language_name(text: str) -> str:
    """A language as one of the fixed names; "Chinese (Mandarin)" is Chinese, others are Other."""
    word = text.split("(")[0].strip().casefold()
    for name in get_args(Language):
        if word == name.casefold():
            return name
    return LANGUAGE_NAMES.get(word, "Other")
