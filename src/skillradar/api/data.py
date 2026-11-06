"""Read the gold tables from the Parquet files that each build exports.

Every request opens its own in-memory DuckDB, so requests never share state and the
warehouse file is never touched.
"""

from pathlib import Path

import duckdb

from skillradar.api.labels import ALL, REGIONS, ROLES

TABLES = ("gold_meta", "gold_scope", "gold_skill_demand")


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
                {
                    "name": name,
                    "postings": postings,
                    "required_postings": required,
                    # float(): DuckDB may return a Decimal, which JSON would turn into text.
                    "share": float(share),
                    "required_share": round(required / total, 4),
                }
                for name, postings, required, share in rows
            ],
        }

    def _connect(self) -> duckdb.DuckDBPyConnection:
        missing = [t for t in TABLES if not (self.folder / f"{t}.parquet").exists()]
        if missing:
            raise NoData(f"no data yet ({', '.join(missing)}), run skillradar-transform")
        con = duckdb.connect()
        for table in TABLES:
            con.read_parquet(str(self.folder / f"{table}.parquet")).create_view(table)
        return con


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
