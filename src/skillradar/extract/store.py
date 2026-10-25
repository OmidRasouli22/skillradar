"""Batches and results on local disk.

Layout under the root folder (data/llm):
    batches/pending/<batch_id>.json   sent, not collected yet
    batches/done/<batch_id>.json      collected
    extractions/<batch_id>.jsonl      one answer per posting
"""

import json
import os
import re
from pathlib import Path

from pydantic import BaseModel

from skillradar.storage import Record, atomic_write, json_line, read_json_lines

# Batch ids come from the API and end up in file names.
BATCH_ID = re.compile(r"[A-Za-z0-9_-]{1,100}")


class PendingBatch(BaseModel):
    batch_id: str
    created_at: str
    model: str
    prompt_version: str
    refnrs: dict[str, str]  # custom_id -> refnr


class ExtractionStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save_pending(self, batch: PendingBatch) -> Path:
        path = self._batch_file("pending", batch.batch_id)
        atomic_write(path, batch.model_dump_json(indent=2).encode("utf-8"))
        return path

    def pending(self) -> list[PendingBatch]:
        folder = self.root / "batches" / "pending"
        return [
            PendingBatch.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(folder.glob("*.json"))
        ]

    def finish(self, batch_id: str, results: list[Record]) -> Path:
        """Save the answers, then move the batch from pending to done."""
        path = self.root / "extractions" / f"{_safe(batch_id)}.jsonl"
        atomic_write(path, "".join(json_line(r) for r in results).encode("utf-8"))
        done = self._batch_file("done", batch_id)
        done.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.replace(self._batch_file("pending", batch_id), done)
        return path

    def done_refnrs(self, model: str, prompt_version: str) -> set[str]:
        """Postings that already have an answer from this model and prompt."""
        done = set()
        for path in self.root.glob("extractions/*.jsonl"):
            for record in read_json_lines(path):
                if record.get("model") == model and record.get("prompt_version") == prompt_version:
                    done.add(record["refnr"])
        return done

    def pending_refnrs(self) -> set[str]:
        return {refnr for batch in self.pending() for refnr in batch.refnrs.values()}

    def results(self) -> list[Record]:
        return [
            r
            for path in sorted(self.root.glob("extractions/*.jsonl"))
            for r in read_json_lines(path)
        ]

    def _batch_file(self, state: str, batch_id: str) -> Path:
        return self.root / "batches" / state / f"{_safe(batch_id)}.json"


def _safe(batch_id: str) -> str:
    if not BATCH_ID.fullmatch(batch_id):
        raise ValueError(f"unexpected batch id: {json.dumps(batch_id)}")
    return batch_id
