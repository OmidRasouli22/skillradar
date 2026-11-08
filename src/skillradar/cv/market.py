"""The open postings the CV is compared with, read from the gold Parquet files.

Same postings and skills as the dashboard: gold_postings, gold_posting_skills (a product
the posting does not name is already left out) and gold_scope for the regions. Skill names
are matched to the skill list again, so a spelling added since the last build counts.
"""

from dataclasses import dataclass
from pathlib import Path

import duckdb

from skillradar.cv.similarity import Similarity
from skillradar.skills.taxonomy import Taxonomy, key

FILES = ("gold_meta", "gold_postings", "gold_posting_skills", "gold_scope")


class NoMarket(Exception):
    pass


@dataclass(frozen=True)
class PostingSkill:
    name: str
    required: bool


@dataclass(frozen=True)
class Posting:
    refnr: str
    title: str
    employer: str | None
    city: str | None
    published: str | None
    role: str
    seniority: str
    remote: str
    german: str  # a level, "unknown" (asked, no level) or "not asked"
    english: str
    regions: frozenset[str]
    skills: tuple[PostingSkill, ...]

    def skill_names(self) -> list[str]:
        return [skill.name for skill in self.skills]


@dataclass(frozen=True)
class Market:
    as_of: str | None
    postings: tuple[Posting, ...]
    similarity: Similarity


def load_market(folder: Path, taxonomy: Taxonomy) -> Market:
    missing = [name for name in FILES if not (folder / f"{name}.parquet").exists()]
    if missing:
        raise NoMarket("no data yet: run skillradar-transform first")
    with duckdb.connect() as con:
        for name in FILES:
            con.read_parquet(str(folder / f"{name}.parquet")).create_view(name)
        [(as_of,)] = con.execute("select as_of from gold_meta").fetchall()
        rows = con.execute(
            "select refnr, title, employer, city, first_published, role, seniority, remote, "
            "german, english from gold_postings order by refnr"
        ).fetchall()
        skill_rows = con.execute(
            "select refnr, skill, required from gold_posting_skills order by refnr, skill"
        ).fetchall()
        region_rows = con.execute(
            "select distinct refnr, region from gold_scope where region != 'all'"
        ).fetchall()
    found: dict[str, dict[str, PostingSkill]] = {}
    for refnr, raw, required in skill_rows:
        name = taxonomy.normalize(raw) or raw
        old = found.setdefault(refnr, {}).get(key(name))
        found[refnr][key(name)] = PostingSkill(name, bool(required) or bool(old and old.required))
    skills = {
        refnr: sorted(by_key.values(), key=lambda s: s.name) for refnr, by_key in found.items()
    }
    regions: dict[str, set[str]] = {}
    for refnr, region in region_rows:
        regions.setdefault(refnr, set()).add(region)
    postings = tuple(
        Posting(
            refnr=row[0],
            title=row[1],
            employer=row[2],
            city=row[3],
            published=row[4].isoformat() if row[4] else None,
            role=row[5],
            seniority=row[6],
            remote=row[7],
            german=row[8],
            english=row[9],
            regions=frozenset(regions.get(row[0], ())),
            skills=tuple(skills.get(row[0], ())),
        )
        for row in rows
    )
    similarity = Similarity(p.skill_names() for p in postings)
    return Market(str(as_of) if as_of else None, postings, similarity)


class MarketCache:
    """Reads the files again only when a build has replaced them."""

    def __init__(self, folder: Path, taxonomy: Taxonomy) -> None:
        self.folder = folder
        self.taxonomy = taxonomy
        self._stamp: tuple[float, ...] | None = None
        self._market: Market | None = None

    def get(self) -> Market:
        try:
            stamp = tuple((self.folder / f"{n}.parquet").stat().st_mtime for n in FILES)
        except FileNotFoundError as error:
            raise NoMarket("no data yet: run skillradar-transform first") from error
        if stamp != self._stamp or self._market is None:
            self._market = load_market(self.folder, self.taxonomy)
            self._stamp = stamp
        return self._market
