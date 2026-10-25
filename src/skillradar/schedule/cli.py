"""Command line: uv run skillradar-schedule install|uninstall|run-now"""

import argparse
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
    install.add_argument(
        "--check-every", type=int, default=60, metavar="MINUTES", help="how often to check"
    )

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
                check_every_minutes=args.check_every,
            )
            path = agent.install(job)
        except (ValueError, RuntimeError) as error:
            print(error, file=sys.stderr)
            return 1
        print(f"installed {path}")
        print(f"runs at login and checks every {job.check_every_minutes} min, once per day")
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
