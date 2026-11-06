"""Read the gold tables from the Parquet files that each build exports.

Every request opens its own in-memory DuckDB, so requests never share state and the
warehouse file is never touched.
"""

from pathlib import Path

import duckdb

from skillradar.api.labels import ALL, REGIONS, ROLES

TABLES = (
    "gold_meta",
    "gold_scope",
    "gold_skill_demand",
    "gold_attribute_shares",
    "gold_emerging_share",
)
# Skills per role on the page, and columns in the role × skill heatmap.
TOP_SKILLS = 30
HEATMAP_SKILLS = 10


class NoData(Exception):
    pass


class GoldData:
    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def overview(self) -> dict:
        with self._connect() as con:
            [meta] = con.execute(
                "select as_of, tech_postings, model, prompt_version from gold_meta"
            ).fetchall()
            roles = con.execute(
                "select role, count(*) from gold_scope where region = ? group by role", [ALL]
            ).fetchall()
            regions = con.execute(
                "select region, count(*) from gold_scope where role = ? group by region", [ALL]
            ).fetchall()
        as_of, tech_postings, model, prompt_version = meta
        return {
            "as_of": as_of.isoformat() if as_of else None,
            "tech_postings": tech_postings,
            "model": model,
            "prompt_version": prompt_version,
            "roles": _choices(roles, ROLES),
            "regions": _choices(regions, REGIONS),
        }

    def skills(self, role: str, region: str, limit: int) -> dict:
        with self._connect() as con:
            [(total,)] = con.execute(
                "select count(*) from gold_scope where role = ? and region = ?", [role, region]
            ).fetchall()
            rows = con.execute(
                "select skill, postings, required_postings, share from gold_skill_demand "
                "where role = ? and region = ? order by postings desc, skill limit ?",
                [role, region, limit],
            ).fetchall()
        return {
            "role": role,
            "region": region,
            "total_postings": total,
            "skills": [
                _skill(name, postings, required, total, share)
                for name, postings, required, share in rows
            ],
        }

    def dashboard(self, region: str) -> dict:
        """Everything the page shows for one region, from one consistent read."""
        with self._connect() as con:
            [meta] = con.execute("select as_of, model, prompt_version from gold_meta").fetchall()
            role_counts = con.execute(
                "select role, count(*) from gold_scope where region = ? group by role", [region]
            ).fetchall()
            skill_rows = con.execute(
                "select role, skill, postings, required_postings, total_postings, share "
                "from (select *, row_number() over "
                "(partition by role order by postings desc, skill) as rank "
                "from gold_skill_demand where region = ?) where rank <= ? "
                "order by role, rank",
                [region, TOP_SKILLS],
            ).fetchall()
            attribute_rows = con.execute(
                "select role, attribute, value, postings, share from gold_attribute_shares "
                "where region = ? order by role, attribute, postings desc, value",
                [region],
            ).fetchall()
            emerging_rows = con.execute(
                "select role, postings, share from gold_emerging_share where region = ?",
                [region],
            ).fetchall()
            emerging_skills = con.execute(
                "select skill, postings, share from gold_skill_demand "
                "where role = ? and region = ? and emerging order by postings desc, skill",
                [ALL, region],
            ).fetchall()
            columns = [name for role, name, *_ in skill_rows if role == ALL][:HEATMAP_SKILLS]
            heatmap_rows = con.execute(
                "select role, skill, share from gold_skill_demand "
                "where region = ? and role != ? and list_contains(?, skill)",
                [region, ALL, columns],
            ).fetchall()
            state_rows = con.execute(
                "select role, region, count(*) from gold_scope where region != ? "
                "group by role, region",
                [ALL],
            ).fetchall()
        as_of, model, prompt_version = meta
        roles = _choices(role_counts, ROLES)
        skills: dict[str, list[dict]] = {}
        for role, name, postings, required, total, share in skill_rows:
            skills.setdefault(role, []).append(_skill(name, postings, required, total, share))
        attributes: dict[str, dict[str, list[dict]]] = {}
        for role, attribute, value, postings, share in attribute_rows:
            values = attributes.setdefault(role, {}).setdefault(attribute, [])
            values.append({"value": value, "postings": postings, "share": float(share)})
        states: dict[str, list[dict]] = {}
        for role, state, postings in state_rows:
            if state in REGIONS:
                states.setdefault(role, []).append(
                    {"id": state, "label": REGIONS[state], "postings": postings}
                )
        return {
            "region": region,
            "as_of": as_of.isoformat() if as_of else None,
            "model": model,
            "prompt_version": prompt_version,
            "total_postings": dict(role_counts).get(ALL, 0),
            "roles": roles,
            "skills": skills,
            "heatmap": _heatmap(columns, heatmap_rows, roles),
            "emerging_skills": [
                {"name": name, "postings": postings, "share": float(share)}
                for name, postings, share in emerging_skills
            ],
            "attributes": attributes,
            "emerging": {
                role: {"postings": postings, "share": float(share)}
                for role, postings, share in emerging_rows
            },
            "states": states,
        }

    def _connect(self) -> duckdb.DuckDBPyConnection:
        missing = [t for t in TABLES if not (self.folder / f"{t}.parquet").exists()]
        if missing:
            raise NoData(f"no data yet ({', '.join(missing)}), run skillradar-transform")
        con = duckdb.connect()
        for table in TABLES:
            con.read_parquet(str(self.folder / f"{table}.parquet")).create_view(table)
        return con


def _skill(name: str, postings: int, required: int, total: int, share) -> dict:
    return {
        "name": name,
        "postings": postings,
        "required_postings": required,
        # float(): DuckDB may return a Decimal, which JSON would turn into text.
        "share": float(share),
        "required_share": round(required / total, 4),
    }


def _heatmap(columns: list[str], rows: list[tuple], roles: list[dict]) -> dict:
    """Share of each role's postings asking for the region's most asked-for skills.

    A role whose postings never ask for a skill gets 0 for it.
    """
    shares = {(role, skill): float(share) for role, skill, share in rows}
    return {
        "skills": columns,
        "rows": [
            {**role, "shares": [shares.get((role["id"], name), 0.0) for name in columns]}
            for role in roles
            if role["id"] != ALL
        ],
    }


def _choices(counts: list[tuple[str, int]], labels: dict[str, str]) -> list[dict]:
    """Known ids with their label and postings: "all" first, "other" last, the rest by size."""
    found = dict(counts)
    choices = [
        {"id": key, "label": label, "postings": found[key]}
        for key, label in labels.items()
        if key in found
    ]
    return sorted(
        choices,
        key=lambda c: (c["id"] != ALL, c["id"] == "other_tech", -c["postings"], c["label"]),
    )
