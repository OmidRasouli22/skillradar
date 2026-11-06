"""Command line: uv run skillradar-web

Starts the page and its API on this Mac only (127.0.0.1).
"""

import argparse

import uvicorn

from skillradar.api.app import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show the SkillRadar page on this Mac.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    print(f"SkillRadar: http://127.0.0.1:{args.port}")
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
