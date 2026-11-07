"""The reference labels: the correct answer for a sample of postings.

eval/labels.jsonl holds one line per posting in the sample, in sample order:
- todo: in the sample, no label yet
- draft: a first label written by a model, not checked yet
- verified: checked and corrected by a person; only these count in the report

Labels follow eval/GUIDE.md, which uses the same rules as the extraction prompt.
"""

import random
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from skillradar.config import PROJECT_ROOT
from skillradar.extract.schema import Extraction, LanguageRequirement, SkillMention, Strict
from skillradar.storage import atomic_write, json_line, read_json_lines

LABELS_PATH = PROJECT_ROOT / "eval" / "labels.jsonl"


def texts_path(data_dir: Path) -> Path:
    """The sample's posting texts, for the review page. Local only, like all texts."""
    return data_dir / "eval" / "texts.jsonl"


Status = Literal["todo", "draft", "verified"]


class Answer(Extraction):
    """The correct answer for one posting. Same shape as Claude's, with size limits."""

    languages: list[LanguageRequirement] = Field(max_length=20)
    skills: list[SkillMention] = Field(max_length=150)


class Label(Strict):
    refnr: str
    status: Status = "todo"
    answer: Answer | None = None
    drafted_by: str | None = None
    verified_at: str | None = None
    note: str = Field(default="", max_length=1000)


class LabelError(Exception):
    pass


class LabelStore:
    """Reads and writes the labels file. Every write replaces the whole file at once."""

    def __init__(self, path: Path = LABELS_PATH) -> None:
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> list[Label]:
        if not self.path.exists():
            return []
        return [Label.model_validate(record) for record in read_json_lines(self.path)]

    def get(self, refnr: str) -> Label | None:
        return next((label for label in self.load() if label.refnr == refnr), None)

    def create(self, refnrs: list[str]) -> None:
        with self._lock:
            if self.path.exists():
                raise LabelError(f"{self.path} already exists; delete it to draw a new sample")
            self._write([Label(refnr=refnr) for refnr in refnrs])

    def add_drafts(self, drafts: dict[str, Answer], by: str) -> int:
        """Save model drafts for postings that are still todo. Returns how many."""
        with self._lock:
            labels = self.load()
            unknown = set(drafts) - {label.refnr for label in labels}
            if unknown:
                raise LabelError(f"not in the sample: {', '.join(sorted(unknown)[:5])}")
            saved = 0
            for label in labels:
                if label.refnr in drafts and label.status == "todo":
                    label.answer = drafts[label.refnr]
                    label.status = "draft"
                    label.drafted_by = by
                    saved += 1
            self._write(labels)
            return saved

    def save(self, refnr: str, answer: Answer, status: Status, note: str = "") -> Label:
        """Save a label from the review page as draft or verified."""
        if status == "todo":
            raise LabelError("a saved label is a draft or verified")
        with self._lock:
            labels = self.load()
            label = next((item for item in labels if item.refnr == refnr), None)
            if label is None:
                raise LabelError(f"not in the sample: {refnr}")
            label.answer = answer
            label.status = status
            label.note = note
            label.verified_at = utc_now() if status == "verified" else None
            self._write(labels)
            return label

    def _write(self, labels: list[Label]) -> None:
        lines = (json_line(label.model_dump(mode="json")) for label in labels)
        atomic_write(self.path, "".join(lines).encode("utf-8"))
        # The labels are meant for the repository, so they are readable like other files.
        self.path.chmod(0o644)


def draw_sample(refnrs: set[str], size: int, seed: int) -> list[str]:
    """A simple random sample; the same refnrs and seed always give the same sample."""
    if size < 1:
        raise LabelError("the sample needs at least one posting")
    if size > len(refnrs):
        raise LabelError(f"only {len(refnrs)} postings to choose from, not {size}")
    # Seeded on purpose: the same seed must give the same sample.
    return random.Random(seed).sample(sorted(refnrs), size)  # noqa: S311


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
