"""The review page's API: check and correct the reference labels (eval/labels.jsonl).

/api/labels                  the sample: status of each posting, and the choices for a label
/api/labels/{refnr}          one posting's text and its label
/api/labels/{refnr}/marks    where the label's skills are in the text (POST, reads only)
/api/labels/{refnr}          save a label as draft or verified (PUT)

Only for the local page (see security.py). The posting texts come from
data/eval/texts.jsonl, never from the warehouse, and Claude's answer is never shown, so it
can't sway the label.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Literal, get_args

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from skillradar.api.postings import REFNR, marks
from skillradar.api.security import local_only, same_page_json
from skillradar.evaluate.labels import Answer, Label, LabelError, LabelStore, texts_path
from skillradar.extract.prompt import ROLES
from skillradar.extract.schema import Language, Level, Remote, Seniority, SkillMention, Strict
from skillradar.skills.taxonomy import Taxonomy
from skillradar.storage import read_json_lines


class SaveRequest(Strict):
    answer: Answer
    status: Literal["draft", "verified"]
    note: str = Field(default="", max_length=1000)


class MarksRequest(Strict):
    skills: list[SkillMention] = Field(max_length=150)


def labeling_router(store: LabelStore, data_dir: Path, taxonomy: Taxonomy) -> APIRouter:
    router = APIRouter(prefix="/api/labels", dependencies=[Depends(local_only)])
    texts = _Texts(texts_path(data_dir))

    @router.get("")
    def sample() -> dict:
        labels = store.load()
        titles = texts.titles()
        return {
            "items": [
                {"refnr": label.refnr, "status": label.status, "title": titles.get(label.refnr)}
                for label in labels
            ],
            "choices": {
                "role": [{"id": role, "hint": hint} for role, hint in ROLES.items()],
                "seniority": list(get_args(Seniority)),
                "remote": list(get_args(Remote)),
                "language": list(get_args(Language)),
                "level": list(get_args(Level)),
            },
            "skills": taxonomy.names(),
        }

    @router.get("/{refnr}")
    def posting(refnr: str) -> dict:
        label = _label(store, refnr)
        text = texts.get(refnr)
        if text is None:
            raise HTTPException(
                status_code=404, detail="no text for this posting; run skillradar-eval texts"
            )
        return {"refnr": refnr, "title": text["title"], "text": text["text"], "label": label}

    @router.post("/{refnr}/marks", dependencies=[Depends(same_page_json)])
    def skill_marks(refnr: str, body: MarksRequest) -> dict:
        _label(store, refnr)
        text = texts.get(refnr)
        if text is None:
            raise HTTPException(status_code=404, detail="no text for this posting")
        skills = [(item.name, item.required) for item in body.skills]
        return {"marks": marks(text["text"], skills, taxonomy)}

    @router.put("/{refnr}", dependencies=[Depends(same_page_json)])
    def save(refnr: str, body: SaveRequest) -> Label:
        _label(store, refnr)
        try:
            return store.save(refnr, body.answer, body.status, body.note)
        except LabelError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router


def _label(store: LabelStore, refnr: str) -> Label:
    if not REFNR.fullmatch(refnr):
        raise HTTPException(status_code=422, detail="invalid reference number")
    label = store.get(refnr)
    if label is None:
        raise HTTPException(status_code=404, detail="not in the sample")
    return label


class _Texts:
    """Posting texts for the sample, read again when the file changes."""

    def __init__(self, path: Path, read: Callable[[Path], list[dict]] | None = None) -> None:
        self.path = path
        self._read = read or (lambda p: list(read_json_lines(p)))
        self._stamp: float | None = None
        self._by_refnr: dict[str, dict] = {}

    def _load(self) -> dict[str, dict]:
        stamp = self.path.stat().st_mtime if self.path.exists() else None
        if stamp != self._stamp:
            records = self._read(self.path) if stamp is not None else []
            self._by_refnr = {
                r["refnr"]: {"title": r.get("title") or "", "text": r["text"]}
                for r in records
                if isinstance(r.get("refnr"), str) and isinstance(r.get("text"), str)
            }
            self._stamp = stamp
        return self._by_refnr

    def get(self, refnr: str) -> dict | None:
        return self._load().get(refnr)

    def titles(self) -> dict[str, str]:
        return {refnr: text["title"] for refnr, text in self._load().items()}
