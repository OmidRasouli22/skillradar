"""Command line: uv run skillradar-schedule install|uninstall|run-now"""

import argparse
import shutil
import sys
from pathlib import Path

from skillradar.config import DATA_DIR, PROJECT_ROOT
from skillradar.schedule.launchd import Job, LaunchAgent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the snapshot every day on this Mac.")
    commands = parser.add_subparsers(dest="command", required=True)

    install = commands.add_parser("install", help="add or update the daily job")
    install.add_argument("--hour", type=int, default=6)
    install.add_argument("--minute", type=int, default=0)

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
            job = Job(
                uv=Path(uv).resolve(),
                project_dir=PROJECT_ROOT,
                log_file=DATA_DIR / "logs" / "snapshot.log",
                hour=args.hour,
                minute=args.minute,
            )
            path = agent.install(job)
        except (ValueError, RuntimeError) as error:
            print(error, file=sys.stderr)
            return 1
        print(f"installed {path}, runs daily at {job.hour:02d}:{job.minute:02d}")
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


if __name__ == "__main__":
    raise SystemExit(main())
