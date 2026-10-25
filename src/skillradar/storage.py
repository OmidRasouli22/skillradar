"""Safe file helpers: private folders, atomic writes, JSON lines."""

import json
import logging
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

Record = dict[str, Any]


def make_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)


def atomic_write(path: Path, data: bytes) -> None:
    """Write to a temp file, then rename, so readers never see half a file."""
    make_private_dir(path.parent)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def json_line(record: Record) -> str:
    return json.dumps(record, ensure_ascii=False) + "\n"


def read_json_lines(path: Path) -> Iterator[Record]:
    """Records from a JSON lines file. Broken lines are skipped with a warning."""
    with path.open(encoding="utf-8") as file:
        for number, line in enumerate(file, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("skipping broken line %d in %s", number, path)
                continue
            if isinstance(record, dict):
                yield record
