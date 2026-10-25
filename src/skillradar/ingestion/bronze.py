"""Raw API data on local disk, one folder per day.

Layout under the root folder:
    search/snapshot_date=YYYY-MM-DD/run_<id>.jsonl.gz search results, compressed
    details/snapshot_date=YYYY-MM-DD/run_<id>.jsonl   full postings
    runs/run_<id>.json                                run summary
"""

import gzip
import json
import os
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from skillradar.storage import Record, atomic_write, json_line, make_private_dir, read_json_lines


@dataclass(frozen=True)
class RunKey:
    """Names files of one run. Built from a UTC time, so names are always safe."""

    started_at: datetime

    def __post_init__(self) -> None:
        if self.started_at.utcoffset() != timedelta(0):
            raise ValueError("started_at must be a UTC time")

    @property
    def run_id(self) -> str:
        return self.started_at.strftime("%Y%m%dT%H%M%SZ")

    @property
    def snapshot_date(self) -> str:
        return self.started_at.date().isoformat()


class BronzeStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write_search(self, run: RunKey, records: Iterable[Record]) -> Path:
        """Search files are large and written once, so they are stored compressed."""
        path = self._run_file("search", run, suffix=".jsonl.gz")
        text = "".join(json_line(record) for record in records)
        atomic_write(path, gzip.compress(text.encode("utf-8"), mtime=0))
        return path

    def compress_search_files(self) -> int:
        """Compress search files written before compression was added."""
        paths = sorted(self.root.glob("search/snapshot_date=*/run_*.jsonl"))
        for path in paths:
            compressed = gzip.compress(path.read_bytes(), mtime=0)
            atomic_write(path.with_name(path.name + ".gz"), compressed)
            path.unlink()
        return len(paths)

    @contextmanager
    def details_writer(self, run: RunKey) -> Iterator[Callable[[Record], None]]:
        """Write details one by one. The file gets its final name even if the run fails,
        so work done before an error is kept."""
        path = self._run_file("details", run)
        part = path.with_name(path.name + ".part")
        make_private_dir(part.parent)
        fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        file = os.fdopen(fd, "w", encoding="utf-8")

        def write(record: Record) -> None:
            file.write(json_line(record))
            file.flush()

        try:
            yield write
        finally:
            file.close()
            os.replace(part, path)

    def recover_unfinished(self) -> int:
        """Keep details from runs that were killed, e.g. when the Mac shut down.
        Only call this while holding the run lock. A broken last line is skipped on read."""
        parts = sorted(self.root.glob("details/snapshot_date=*/run_*.jsonl.part"))
        for part in parts:
            os.replace(part, part.with_suffix(""))
        return len(parts)

    def known_refnrs(self) -> set[str]:
        """Refnrs that already have a details record from an earlier run."""
        known: set[str] = set()
        for path in sorted(self.root.glob("details/snapshot_date=*/run_*.jsonl")):
            for record in read_json_lines(path):
                refnr = record.get("refnr")
                if isinstance(refnr, str):
                    known.add(refnr)
        return known

    def write_run_log(self, run: RunKey, summary: Record) -> Path:
        path = self.root / "runs" / f"run_{run.run_id}.json"
        text = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
        atomic_write(path, text.encode("utf-8"))
        return path

    def has_finished_run(self, snapshot_date: str) -> bool:
        """True if a full run on this UTC day ended ok or partial. Failed days are retried."""
        day = snapshot_date.replace("-", "")
        for path in self.root.glob(f"runs/run_{day}T*.json"):
            try:
                log = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if log.get("full_scope") and log.get("status") in ("ok", "partial"):
                return True
        return False

    def _run_file(self, kind: str, run: RunKey, suffix: str = ".jsonl") -> Path:
        folder = self.root / kind / f"snapshot_date={run.snapshot_date}"
        return folder / f"run_{run.run_id}{suffix}"
