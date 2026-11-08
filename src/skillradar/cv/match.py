"""Compare a CV profile with the open postings.

For every posting in the chosen role and region:

    skills    = covered weight / total weight of the posting's skills
                (required skills weigh 1, nice-to-have skills 0.4)
    match     = skills x language fit x seniority fit

A skill is covered by the CV itself (by how strongly the CV shows it, see
profile.strength), by a skill that proves it (AWS proves Cloud Computing), or partly by
a substitute (AWS for Azure, at most half). Postings that name fewer than three skills are
not scored: covering one or two skills says little about fitting a job.

The gap analysis asks for each missing skill: if the person learned it in a solid
project, how many postings would become at least a good match? That number ranks the
skills to learn, so a skill counts by the jobs it opens, not by how often it is asked.
"""

import math
from dataclasses import dataclass
from statistics import median

from skillradar.api.labels import ALL, REGIONS, ROLES
from skillradar.cv.families import SkillFamilies
from skillradar.cv.market import Market, Posting
from skillradar.cv.profile import CvProfile, language_levels, strength
from skillradar.cv.similarity import Similarity
from skillradar.skills.taxonomy import Taxonomy, key

REQUIRED_WEIGHT = 1.0
NICE_WEIGHT = 0.4
# A substitute counts at most half, scaled by how alike the two skills are in postings.
SUBSTITUTE_MAX = 0.5
# Likeness used when a skill is too rare in the postings to measure.
SUBSTITUTE_DEFAULT_LIKENESS = 0.6
# A skill the person learns in a solid project, for the gap analysis.
LEARNED_STRENGTH = 0.8
BANDS = (("strong", 0.70), ("good", 0.50), ("partial", 0.30), ("weak", 0.0))
GOOD = 0.50
MIN_SKILLS = 3
# A skill is a gap candidate when at least this many scored postings ask for it.
MIN_GAP_POSTINGS = 3
MIN_GAP_SHARE = 0.01
GAPS_SHOWN = 15
MATCHES_SHOWN = 30
DEMAND_SHOWN = 30
# A known skill is named as a base for a missing one from this likeness up.
BUILDS_ON_LIKENESS = 0.55

LEVEL_RANK = {"basic": 1, "good": 2, "fluent": 3, "native": 4}
# "Asked, no level" in a posting and "no level" in a CV are read as good (B2).
UNKNOWN_RANK = 2
SENIORITY_RANK = {"student": 0, "junior": 1, "mid": 2, "senior": 3, "lead": 4}
LANGUAGES = (("German", "german"), ("English", "english"))


@dataclass(frozen=True)
class Credit:
    value: float  # 0 to 1
    kind: str  # have | proven | substitute | missing
    via: str | None = None  # the CV skill that proves or replaces it


MISSING = Credit(0.0, "missing")


class Credits:
    """How well a CV covers any skill name. Built once per profile."""

    def __init__(
        self,
        profile: CvProfile,
        families: SkillFamilies,
        similarity: Similarity,
        this_year: int,
        taxonomy: Taxonomy,
    ) -> None:
        self.similarity = similarity
        self.taxonomy = taxonomy
        self.have: dict[str, tuple[str, float]] = {}
        for skill in profile.skills:
            name = taxonomy.normalize(skill.name) or skill.name
            k, value = key(name), strength(skill, this_year)
            if k not in self.have or value > self.have[k][1]:
                self.have[k] = (name, value)
        self._proving = families.proving()
        self._substitutes = families.substitutes()
        self._cache: dict[str, Credit] = {}

    def of(self, name: str) -> Credit:
        name = self.taxonomy.normalize(name) or name
        k = key(name)
        if k not in self._cache:
            self._cache[k] = self._find(name, k)
        return self._cache[k]

    def _find(self, name: str, k: str) -> Credit:
        best = MISSING
        if k in self.have:
            best = Credit(self.have[k][1], "have")
        for product in self._proving.get(k, ()):
            found = self.have.get(key(product))
            if found and found[1] > best.value:
                best = Credit(found[1], "proven", found[0])
        for other in sorted(self._substitutes.get(k, ())):
            found = self.have.get(key(other))
            if not found:
                continue
            likeness = self.similarity.of(name, other)
            likeness = SUBSTITUTE_DEFAULT_LIKENESS if likeness is None else likeness
            value = round(SUBSTITUTE_MAX * likeness * found[1], 4)
            if value > best.value:
                best = Credit(value, "substitute", found[0])
        return best


@dataclass
class Scored:
    posting: Posting
    skills: float
    language: float
    seniority: float
    total_weight: float

    @property
    def match(self) -> float:
        return self.skills * self.language * self.seniority


def band(value: float) -> str:
    return next(name for name, low in BANDS if value >= low)


def language_fit(needed: str, have: str | None) -> float:
    """1 when the CV meets the level, 0.7 one level short, 0.4 two or more or missing."""
    if needed == "not asked":
        return 1.0
    need = LEVEL_RANK.get(needed, UNKNOWN_RANK)
    rank = 0 if have is None else LEVEL_RANK.get(have, UNKNOWN_RANK)
    short = need - rank
    return 1.0 if short <= 0 else 0.7 if short == 1 else 0.4


def seniority_fit(posting: str, person: str) -> float:
    """1 for the same level; a step up is a stretch, far below is overqualified."""
    if posting not in SENIORITY_RANK or person not in SENIORITY_RANK:
        return 1.0
    if posting == "student":
        return 1.0 if person == "student" else 0.5  # working students must be enrolled
    if person == "student":
        return {"junior": 0.85, "mid": 0.6}.get(posting, 0.3)
    gap = SENIORITY_RANK[posting] - SENIORITY_RANK[person]
    if gap == 0:
        return 1.0
    if gap == 1:
        return 0.8
    if gap >= 2:
        return 0.5
    return 0.9 if gap == -1 else 0.7


def weight(required: bool) -> float:
    return REQUIRED_WEIGHT if required else NICE_WEIGHT


def score(posting: Posting, credits: Credits, levels: dict[str, str], seniority: str) -> Scored:
    total = sum(weight(s.required) for s in posting.skills)
    covered = sum(weight(s.required) * credits.of(s.name).value for s in posting.skills)
    language = 1.0
    for language_name, field in LANGUAGES:
        language *= language_fit(getattr(posting, field), levels.get(language_name))
    return Scored(
        posting=posting,
        skills=covered / total if total else 0.0,
        language=language,
        seniority=seniority_fit(posting.seniority, seniority),
        total_weight=total,
    )


def in_scope(posting: Posting, role: str, region: str) -> bool:
    if posting.role == "not_tech":
        return False
    if role != ALL and posting.role != role:
        return False
    return region == ALL or region in posting.regions


def analyse(
    profile: CvProfile,
    market: Market,
    families: SkillFamilies,
    role: str,
    region: str,
    this_year: int,
    taxonomy: Taxonomy,
) -> dict:
    credits = Credits(profile, families, market.similarity, this_year, taxonomy)
    levels = language_levels(profile)
    in_region = [p for p in market.postings if in_scope(p, ALL, region)]
    scored_region = [
        score(p, credits, levels, profile.seniority)
        for p in in_region
        if len(p.skills) >= MIN_SKILLS
    ]
    scope = [s for s in scored_region if role == ALL or s.posting.role == role]
    all_in_scope = sum(1 for p in in_region if role == ALL or p.role == role)
    matches = [s.match for s in scope]
    return {
        "role": role,
        "role_label": ROLES.get(role, role),
        "region": region,
        "region_label": REGIONS.get(region, region),
        "as_of": market.as_of,
        "summary": {
            "postings": all_in_scope,
            "scored": len(scope),
            "bands": {name: sum(1 for m in matches if band(m) == name) for name, _ in BANDS},
            "median": round(median(matches), 4) if matches else None,
            "good_or_better": sum(1 for m in matches if m >= GOOD),
        },
        "roles": role_fit(scored_region),
        "demand": demand(scope, credits, profile),
        "gaps": gaps(scope, credits, levels, profile, market.similarity),
        "matches": best_matches(scope, credits, levels),
    }


def role_fit(scored: list[Scored]) -> list[dict]:
    """Per role: how many postings are at least a good match."""
    by_role: dict[str, list[float]] = {}
    for s in scored:
        by_role.setdefault(s.posting.role, []).append(s.match)
    rows = [
        {
            "id": role,
            "label": ROLES.get(role, role),
            "scored": len(values),
            "good_or_better": sum(1 for v in values if v >= GOOD),
            "share": round(sum(1 for v in values if v >= GOOD) / len(values), 4),
            "median": round(median(values), 4),
        }
        for role, values in by_role.items()
        if role in ROLES
    ]
    return sorted(rows, key=lambda r: (-r["share"], -r["scored"], r["id"]))


def demand(scope: list[Scored], credits: Credits, profile: CvProfile) -> list[dict]:
    """The most asked-for skills in the scope and how the CV covers each."""
    counts: dict[str, list] = {}
    for s in scope:
        for skill in s.posting.skills:
            entry = counts.setdefault(key(skill.name), [skill.name, 0, 0])
            entry[1] += 1
            entry[2] += skill.required
    evidence = {
        key(credits.taxonomy.normalize(skill.name) or skill.name): skill for skill in profile.skills
    }
    rows = sorted(counts.values(), key=lambda e: (-e[1], e[0]))[:DEMAND_SHOWN]
    total = len(scope)
    result = []
    for name, postings, required in rows:
        credit = credits.of(name)
        cv_skill = evidence.get(key(name))
        result.append(
            {
                "skill": name,
                "postings": postings,
                "required_postings": required,
                "share": round(postings / total, 4) if total else 0.0,
                "coverage": _credit(credit),
                "evidence": cv_skill.evidence if cv_skill and credit.kind == "have" else None,
            }
        )
    return result


def gaps(
    scope: list[Scored],
    credits: Credits,
    levels: dict[str, str],
    profile: CvProfile,
    similarity: Similarity,
) -> list[dict]:
    """Skills and languages ranked by how many postings they would make a good match."""
    if not scope:
        return []
    asked: dict[str, list] = {}
    for s in scope:
        for skill in s.posting.skills:
            asked.setdefault(key(skill.name), [skill.name, []])[1].append((s, skill.required))
    least = max(MIN_GAP_POSTINGS, math.ceil(MIN_GAP_SHARE * len(scope)))
    results = []
    for name, uses in asked.values():
        credit = credits.of(name)
        if credit.kind in ("have", "proven") or len(uses) < least:
            continue
        gained, total_gain = 0, 0.0
        for s, required in uses:
            change = weight(required) * (LEARNED_STRENGTH - credit.value) / s.total_weight
            after = (s.skills + change) * s.language * s.seniority
            gained += s.match < GOOD <= after
            total_gain += after - s.match
        results.append(
            {
                "kind": "skill",
                "name": name,
                "postings": len(uses),
                "required_postings": sum(1 for _, r in uses if r),
                "share": round(len(uses) / len(scope), 4),
                "coverage": _credit(credit),
                "gained": gained,
                "mean_gain": round(total_gain / len(scope), 4),
                "builds_on": _builds_on(name, credits, similarity),
            }
        )
    results += _language_gaps(scope, levels)
    results.sort(key=lambda g: (-g["gained"], -g["mean_gain"], -g["postings"], g["name"]))
    return [g for g in results if g["gained"] > 0 or g["mean_gain"] > 0][:GAPS_SHOWN]


def _language_gaps(scope: list[Scored], levels: dict[str, str]) -> list[dict]:
    """What reaching fluent (C1) German or English would open."""
    results = []
    for language_name, field in LANGUAGES:
        have = levels.get(language_name)
        if have is not None and LEVEL_RANK.get(have, UNKNOWN_RANK) >= LEVEL_RANK["fluent"]:
            continue
        gained, total_gain, asking = 0, 0.0, 0
        for s in scope:
            needed = getattr(s.posting, field)
            if needed == "not asked":
                continue
            asking += 1
            before = language_fit(needed, have)
            after_fit = language_fit(needed, "fluent")
            if after_fit == before:
                continue
            after = s.skills * (s.language / before * after_fit) * s.seniority
            gained += s.match < GOOD <= after
            total_gain += after - s.match
        if asking:
            results.append(
                {
                    "kind": "language",
                    "name": f"{language_name} (fluent, C1)",
                    "postings": asking,
                    "required_postings": asking,
                    "share": round(asking / len(scope), 4),
                    # via: the level the CV has now, if any
                    "coverage": {
                        "kind": "missing" if have is None else "lower",
                        "via": have,
                        "value": 0.0,
                    },
                    "gained": gained,
                    "mean_gain": round(total_gain / len(scope), 4),
                    "builds_on": [],
                }
            )
    return results


def _builds_on(name: str, credits: Credits, similarity: Similarity) -> list[str]:
    """Up to three of the person's skills that appear in the same kind of jobs."""
    found = []
    for known, _ in credits.have.values():
        likeness = similarity.of(name, known)
        if likeness is not None and likeness >= BUILDS_ON_LIKENESS:
            found.append((likeness, known))
    return [known for _, known in sorted(found, key=lambda f: (-f[0], f[1]))[:3]]


def best_matches(scope: list[Scored], credits: Credits, levels: dict[str, str]) -> list[dict]:
    ranked = sorted(scope, key=lambda s: (-s.match, -(_day(s.posting.published)), s.posting.refnr))[
        :MATCHES_SHOWN
    ]
    return [_match(s, credits, levels) for s in ranked]


def _day(published: str | None) -> int:
    return int(published.replace("-", "")) if published else 0


def _match(s: Scored, credits: Credits, levels: dict[str, str]) -> dict:
    p = s.posting
    skills = [
        {
            "skill": skill.name,
            "required": skill.required,
            "coverage": _credit(credits.of(skill.name)),
        }
        for skill in sorted(p.skills, key=lambda k: (not k.required, k.name.casefold()))
    ]
    languages = [
        {"language": name, "needed": getattr(p, field), "have": levels.get(name)}
        for name, field in LANGUAGES
        if getattr(p, field) != "not asked"
    ]
    return {
        "refnr": p.refnr,
        "title": p.title,
        "employer": p.employer,
        "city": p.city,
        "regions": len(p.regions),
        "published": p.published,
        "role": p.role,
        "seniority": p.seniority,
        "remote": p.remote,
        "match": round(s.match, 4),
        "band": band(s.match),
        "parts": {
            "skills": round(s.skills, 4),
            "language": round(s.language, 4),
            "seniority": round(s.seniority, 4),
        },
        "skills": skills,
        "languages": languages,
    }


def _credit(credit: Credit) -> dict:
    return {"kind": credit.kind, "via": credit.via, "value": round(credit.value, 4)}
