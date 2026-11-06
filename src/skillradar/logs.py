"""Logging setup shared by all commands."""

import logging
import sys


def setup_logging() -> None:
    # stdout, like dbt. Two streams into one log file can overwrite each other's lines.
    # force: importing dbt already adds a handler, which would make basicConfig do nothing.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
        force=True,
    )
    # One line per HTTP request is too much for the hourly log. The Anthropic SDK uses httpx2.
    for name in ("httpx", "httpx2"):
        logging.getLogger(name).setLevel(logging.WARNING)
