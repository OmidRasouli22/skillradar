"""Stop two runs from writing to the same data at once."""

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class AlreadyRunning(Exception):
    pass


@contextmanager
def run_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive lock on `path`. The OS frees it if the process dies."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise AlreadyRunning(f"another run holds {path}") from error
        yield
    finally:
        os.close(fd)
