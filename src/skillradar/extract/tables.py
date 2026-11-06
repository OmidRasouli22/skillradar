"""Rows for the silver tables built from saved answers (transform/models/silver).

Only answers from the current model and prompt version are used, so all rows come from
the same instructions. Older answers stay on disk for comparison.
"""

from pathlib import Path

from skillradar.extract.prompt import PROMPT_VERSION
from skillradar.extract.settings import load_settings
from skillradar.extract.store import ExtractionStore
from skillradar.skills.matching import prepare, written_in
from skillradar.skills.taxonomy import Taxonomy
from skillradar.storage import Record


def load_current_answers(llm_dir: Path, refnrs: set[str]) -> list[Record]:
    """Answers for the configured model and the prompt in the code, for known postings."""
    results = ExtractionStore(llm_dir).results()
    answers = current_answers(results, load_settings().model, PROMPT_VERSION)
    return [a for a in answers if a["refnr"] in refnrs]


def current_answers(results: list[Record], model: str, prompt_version: str) -> list[Record]:
    """The newest ok answer per posting for this model and prompt version."""
    newest: dict[str, Record] = {}
    for record in results:
        if record["model"] != model or record["prompt_version"] != prompt_version:
            continue
        if record["status"] != "ok":
            continue
        old = newest.get(record["refnr"])
        if old is None or record["extracted_at"] > old["extracted_at"]:
            newest[record["refnr"]] = record
    return [newest[refnr] for refnr in sorted(newest)]


def posting_rows(answers: list[Record]) -> list[Record]:
    return [
        {
            "refnr": a["refnr"],
            "role": a["output"]["role"],
            "seniority": a["output"]["seniority"],
            "remote": a["output"]["remote"],
            "model": a["model"],
            "prompt_version": a["prompt_version"],
            "extracted_at": a["extracted_at"],
        }
        for a in answers
    ]


def language_rows(answers: list[Record]) -> list[Record]:
    rows = {}
    for a in answers:
        for item in a["output"]["languages"]:
            # One row per language; a second mention keeps the first level.
            rows.setdefault((a["refnr"], item["language"]), item["level"])
    return [
        {"refnr": refnr, "language": language, "level": level}
        for (refnr, language), level in rows.items()
    ]


def skill_rows(answers: list[Record], taxonomy: Taxonomy, texts: dict[str, str]) -> list[Record]:
    """One row per posting and skill.

    skill is the name from config/skills.yaml when it is in the list, else Claude's name.
    in_text says if the posting names the skill or one of its spellings. general says if
    the skill is a concept, not a product. A concept can be missing from the text for a
    good reason ("Networking" for "Netzwerk"); a product that is missing was most likely
    added by the model.
    """
    rows: dict[tuple[str, str], Record] = {}
    for a in answers:
        text = prepare(texts.get(a["refnr"], ""))
        for item in a["output"]["skills"]:
            raw = " ".join(item["name"].split())
            name = taxonomy.normalize(raw) or raw
            key = (a["refnr"], name.casefold())
            if key in rows:
                rows[key]["required"] = rows[key]["required"] or item["required"]
                continue
            terms = {raw, *taxonomy.spellings_of(name)}
            rows[key] = {
                "refnr": a["refnr"],
                "skill": name,
                "category": taxonomy.category_of(name),
                "general": taxonomy.is_general(name),
                "emerging": taxonomy.is_emerging(name),
                "required": item["required"],
                "in_skill_list": taxonomy.normalize(raw) is not None,
                "in_text": any(written_in(text, term) for term in terms),
            }
    return list(rows.values())
