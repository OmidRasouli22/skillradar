"""Command line: uv run skillradar-schedule install|uninstall|run-now"""

import argparse
import re
import shutil
import sys
from pathlib import Path

from skillradar.config import DATA_DIR, PROJECT_ROOT
from skillradar.schedule.launchd import Job, LaunchAgent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the snapshot once a day on this Mac, as soon as it is on."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    install = commands.add_parser("install", help="add or update the daily job")
    install.add_argument("--at", default="08:00", metavar="HH:MM", help="time of day to run")

    commands.add_parser("uninstall", help="remove the daily job")
    commands.add_parser("run-now", help="start the installed job once, right now")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, agent: LaunchAgent | None = None) -> int:
    args = parse_args(argv)
    agent = agent or LaunchAgent()

    if args.command == "install":
        uv = shutil.which("uv")
        if uv is None:
            print("uv not found on PATH", file=sys.stderr)
            return 1
        try:
            hour, minute = _time_of_day(args.at)
            job = Job(
                uv=Path(uv).resolve(),
                project_dir=PROJECT_ROOT,
                log_file=DATA_DIR / "logs" / "snapshot.log",
                hour=hour,
                minute=minute,
            )
            path = agent.install(job)
        except (ValueError, RuntimeError) as error:
            print(error, file=sys.stderr)
            return 1
        print(f"installed {path}")
        print(f"runs every day at {job.hour:02d}:{job.minute:02d}, or at login if that was missed")
        print(f"log: {job.log_file}")

    elif args.command == "uninstall":
        print("removed" if agent.uninstall() else "not installed")

    elif args.command == "run-now":
        try:
            agent.run_now()
        except RuntimeError as error:
            print(error, file=sys.stderr)
            return 1
        print("started, see data/logs/snapshot.log")

    return 0


def _time_of_day(text: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not match:
        raise ValueError(f"invalid time: {text} (use HH:MM, e.g. 08:00)")
    return int(match.group(1)), int(match.group(2))


if __name__ == "__main__":
    raise SystemExit(main())
