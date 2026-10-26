import logging
import sys

from skillradar.logs import setup_logging


def test_replaces_handlers_added_by_other_libraries():
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    try:
        root.addHandler(logging.NullHandler())  # what importing dbt does
        setup_logging()

        [handler] = root.handlers
        assert isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout
        assert root.level == logging.INFO
    finally:
        root.handlers[:], _ = saved
        root.setLevel(saved[1])
