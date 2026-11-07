"""Write everything the public page needs as JSON files.

Layout under the site folder:
    data/overview.json                 data date, roles and regions
    data/dashboard/<region>.json       the charts for one region
    data/postings/<role>/<region>.json the job list for one role and region
    data/jobs/<refnr>.json             one job's profile, without its text
    data/health.json                   pipeline health (skillradar.health)

Full posting texts stay local: employers own them, and a contact name can slip through
the cleaning. The public job view links to the original posting instead.
"""

import json
from pathlib import Path

from skillradar.api.data import GoldData
from skillradar.api.labels import REGIONS
from skillradar.api.postings import REFNR


def export_data(gold: GoldData, folder: Path) -> dict[str, int]:
    """Write the data files into folder/data. Returns how many files of each kind."""
    data = folder / "data"
    overview = gold.overview()
    _write(data / "overview.json", overview)

    for region in REGIONS:
        _write(data / "dashboard" / f"{region}.json", gold.dashboard(region))

    lists = 0
    for role in (r["id"] for r in overview["roles"]):
        for region in REGIONS:
            postings = gold.postings(role, region, 0, 100_000)
            if postings["total"] == 0:
                continue  # the page shows "no postings" when a list is missing
            _write(data / "postings" / role / f"{region}.json", postings)
            lists += 1

    jobs = 0
    for refnr, profile in gold.profiles().items():
        if not REFNR.fullmatch(refnr):
            continue  # never let a strange number become a file path
        _write(data / "jobs" / f"{refnr}.json", {**profile, "text": "", "marks": []})
        jobs += 1
    return {"regions": len(REGIONS), "lists": lists, "jobs": jobs}


def write_health(health: dict, folder: Path) -> None:
    _write(folder / "data" / "health.json", health)


def _write(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, separators=(",", ":")), "utf-8")
