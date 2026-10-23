"""Desktop notifications on macOS."""

import logging
import subprocess
import sys
from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)

Runner = Callable[[Sequence[str]], object]

# Title and message are passed as arguments, never put into the script text,
# so text from the API cannot change what the script does.
APPLESCRIPT = [
    "on run argv",
    "display notification (item 2 of argv) with title (item 1 of argv)",
    "end run",
]


def _run(args: Sequence[str]) -> object:
    return subprocess.run(args, check=True, capture_output=True, timeout=10)  # noqa: S603


def notify(title: str, message: str, runner: Runner = _run, platform: str = sys.platform) -> None:
    if platform != "darwin":
        return
    args = ["/usr/bin/osascript"]
    for line in APPLESCRIPT:
        args += ["-e", line]
    args += ["--", title, message[:200]]
    try:
        runner(args)
    except (OSError, subprocess.SubprocessError) as error:
        logger.warning("could not show notification: %s", error)
