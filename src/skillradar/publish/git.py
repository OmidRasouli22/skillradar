"""Push the site folder to the GitHub Pages branch as one new commit.

The folder gets its own small git repository each time, and its single commit replaces
the branch on GitHub (force push). The branch never collects old versions, so the
repository does not grow day by day.
"""

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess]


class PublishError(Exception):
    pass


def _run(args: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=False, capture_output=True, text=True, timeout=300)  # noqa: S603


def remote_url(project: Path, remote: str, run: Runner = _run) -> str:
    result = run(["git", "-C", str(project), "remote", "get-url", remote])
    if result.returncode != 0:
        raise PublishError(f"no git remote '{remote}': {result.stderr.strip()}")
    return result.stdout.strip()


def push(folder: Path, url: str, branch: str, message: str, run: Runner = _run) -> None:
    git = ["git", "-C", str(folder)]
    steps = [
        [*git, "init", "-q", "-b", branch],
        [*git, "add", "-A"],
        [*git, "commit", "-q", "-m", message],
        [*git, "push", "-q", "--force", url, f"{branch}:{branch}"],
    ]
    for args in steps:
        result = run(args)
        if result.returncode != 0:
            raise PublishError(f"{' '.join(args[3:5])} failed: {result.stderr.strip()[:300]}")
