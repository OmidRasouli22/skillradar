"""Load config/skills.yaml and map any spelling of a skill to one name."""

import re
from functools import cached_property
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from skillradar.config import PROJECT_ROOT

DEFAULT_SKILLS_PATH = PROJECT_ROOT / "config" / "skills.yaml"

# A match must not touch letters or digits, so "Java" is not found in "JavaScript".
# "#" and "+" count as part of a name, so "C" is not found in "C#" or "C++".
BEFORE = r"(?<![\w#+.])"
AFTER = r"(?![\w#+])"


def key(text: str) -> str:
    """Lookup key: case, hyphens, underscores and extra spaces do not matter."""
    return " ".join(text.casefold().replace("-", " ").replace("_", " ").split())


class Skill(BaseModel):
    name: str = Field(min_length=1)
    category: str
    aliases: list[str] = Field(default_factory=list)
    ambiguous: bool = False

    def spellings(self) -> list[str]:
        return [self.name, *self.aliases]

    def search_terms(self) -> list[str]:
        """Spellings safe for keyword search. Ambiguous names are left out."""
        return self.aliases if self.ambiguous else self.spellings()


class Taxonomy(BaseModel):
    categories: dict[str, str]
    skills: list[Skill] = Field(min_length=1)

    @model_validator(mode="after")
    def check(self) -> "Taxonomy":
        owners: dict[str, str] = {}
        for skill in self.skills:
            if skill.category not in self.categories:
                raise ValueError(f"{skill.name}: unknown category {skill.category!r}")
            for spelling in skill.spellings():
                k = key(spelling)
                if k in owners and owners[k] != skill.name:
                    raise ValueError(f"{spelling!r} is used by {owners[k]} and {skill.name}")
                owners[k] = skill.name
        return self

    @cached_property
    def _by_key(self) -> dict[str, str]:
        return {key(s): skill.name for skill in self.skills for s in skill.spellings()}

    @cached_property
    def _pattern(self) -> re.Pattern[str]:
        terms = {term: skill.name for skill in self.skills for term in skill.search_terms()}
        # Longest first, so "Apache Spark" wins over "Spark" and "C++" over "C".
        ordered = sorted(terms, key=len, reverse=True)
        body = "|".join(_flexible(term) for term in ordered)
        return re.compile(f"{BEFORE}(?:{body}){AFTER}", re.IGNORECASE)

    @cached_property
    def _by_term(self) -> dict[str, str]:
        # Without spaces, because the search also finds "RESTAPI" for "REST API".
        return {_compact(t): skill.name for skill in self.skills for t in skill.search_terms()}

    def names(self) -> list[str]:
        return [skill.name for skill in self.skills]

    def category_of(self, name: str) -> str | None:
        return next((s.category for s in self.skills if s.name == name), None)

    def normalize(self, raw: str) -> str | None:
        """The skill name for any spelling, or None if it is not in the list."""
        return self._by_key.get(key(raw)) if raw else None

    def find_in_text(self, text: str) -> set[str]:
        """Simple keyword search. Used to check the list and as a baseline for the LLM."""
        return {self._by_term[_compact(m.group(0))] for m in self._pattern.finditer(text)}


def _compact(text: str) -> str:
    return key(text).replace(" ", "")


def _flexible(term: str) -> str:
    """Regex for a term where a space or hyphen may be a space, a hyphen or nothing."""
    parts = re.split(r"[\s-]+", term)
    return r"[\s-]?".join(re.escape(part) for part in parts)


def load_taxonomy(path: Path = DEFAULT_SKILLS_PATH) -> Taxonomy:
    with path.open(encoding="utf-8") as f:
        return Taxonomy.model_validate(yaml.safe_load(f))
