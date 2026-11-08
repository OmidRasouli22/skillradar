"""Load config/skill_families.yaml: which skills prove or replace which (see that file)."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from skillradar.config import PROJECT_ROOT
from skillradar.skills.taxonomy import Taxonomy, key

DEFAULT_FAMILIES_PATH = PROJECT_ROOT / "config" / "skill_families.yaml"


class SkillFamilies(BaseModel):
    implies: dict[str, list[str]] = Field(default_factory=dict)
    families: list[list[str]] = Field(default_factory=list)

    def check(self, taxonomy: Taxonomy) -> "SkillFamilies":
        """Every name must be in the skill list, every family must have two or more skills."""
        known = set(taxonomy.names())
        names = [*self.implies, *(n for v in self.implies.values() for n in v)]
        names += [n for family in self.families for n in family]
        unknown = sorted({n for n in names if n not in known})
        if unknown:
            raise ValueError(f"not in config/skills.yaml: {', '.join(unknown)}")
        for concept, products in self.implies.items():
            if concept in products:
                raise ValueError(f"{concept} implies itself")
        for family in self.families:
            if len(set(family)) < 2 or len(set(family)) != len(family):
                raise ValueError(f"a family needs two or more different skills: {family}")
        return self

    def proving(self) -> dict[str, list[str]]:
        """For each broader skill (by key), the skills that prove it."""
        return {key(concept): products for concept, products in self.implies.items()}

    def substitutes(self) -> dict[str, set[str]]:
        """For each skill (by key), the skills that can partly replace it."""
        found: dict[str, set[str]] = {}
        for family in self.families:
            for name in family:
                found.setdefault(key(name), set()).update(n for n in family if n != name)
        return found


def load_families(taxonomy: Taxonomy, path: Path = DEFAULT_FAMILIES_PATH) -> SkillFamilies:
    with path.open(encoding="utf-8") as f:
        return SkillFamilies.model_validate(yaml.safe_load(f)).check(taxonomy)
