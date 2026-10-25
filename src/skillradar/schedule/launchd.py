"""Daily job for macOS launchd.

launchd skips a fixed time when the Mac is off. So the job starts at login and then every
hour, and the snapshot itself does nothing when today already has a full run.
"""

import os
import plistlib
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

LABEL = "com.skillradar.snapshot"
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess]


@dataclass(frozen=True)
class Job:
    uv: Path
    project_dir: Path
    log_file: Path
    check_every_minutes: int = 60

    def __post_init__(self) -> None:
        if not 5 <= self.check_every_minutes <= 24 * 60:
            raise ValueError(f"invalid check interval: {self.check_every_minutes} minutes")
        for path in (self.uv, self.project_dir, self.log_file):
            if not path.is_absolute():
                raise ValueError(f"path must be absolute: {path}")


def build_plist(job: Job) -> bytes:
    return plistlib.dumps(
        {
            "Label": LABEL,
            "ProgramArguments": [
                # Keeps the Mac from going to sleep while the run is going.
                "/usr/bin/caffeinate",
                "-i",
                str(job.uv),
                "run",
                "--project",
                str(job.project_dir),
                "skillradar-snapshot",
                "--notify",
                "--once-per-day",
            ],
            "WorkingDirectory": str(job.project_dir),
            "RunAtLoad": True,
            "StartInterval": job.check_every_minutes * 60,
            "StandardOutPath": str(job.log_file),
            "StandardErrorPath": str(job.log_file),
            "ProcessType": "Background",
        }
    )


def _run(args: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=False, capture_output=True, text=True)  # noqa: S603


class LaunchAgent:
    def __init__(self, agents_dir: Path = LAUNCH_AGENTS, runner: Runner = _run) -> None:
        self.plist_path = agents_dir / f"{LABEL}.plist"
        self._runner = runner
        self._domain = f"gui/{os.getuid()}"

    def install(self, job: Job) -> Path:
        job.log_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.plist_path.parent.mkdir(parents=True, exist_ok=True)
        self._unload()
        self.plist_path.write_bytes(build_plist(job))
        self.plist_path.chmod(0o644)
        result = self._runner(["/bin/launchctl", "bootstrap", self._domain, str(self.plist_path)])
        if result.returncode != 0:
            raise RuntimeError(f"launchctl bootstrap failed: {result.stderr.strip()}")
        return self.plist_path

    def uninstall(self) -> bool:
        """Remove the job. Returns False if it was not installed."""
        if not self.plist_path.exists():
            return False
        self._unload()
        self.plist_path.unlink()
        return True

    def run_now(self) -> None:
        result = self._runner(["/bin/launchctl", "kickstart", f"{self._domain}/{LABEL}"])
        if result.returncode != 0:
            raise RuntimeError(f"launchctl kickstart failed: {result.stderr.strip()}")

    def _unload(self) -> None:
        # Fails when the job is not loaded, which is fine.
        self._runner(["/bin/launchctl", "bootout", f"{self._domain}/{LABEL}"])
