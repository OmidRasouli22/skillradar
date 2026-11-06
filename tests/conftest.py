from collections.abc import Callable

import httpx
import pytest

from skillradar.config import load_config
from skillradar.ingestion.client import JobsucheClient

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    """Git in tests ignores the user's git config and always has a commit identity."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "SkillRadar Tests")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "tests@skillradar.invalid")


@pytest.fixture
def api_config():
    return load_config().api


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def make_client(api_config, sleeps) -> Callable[[Handler], JobsucheClient]:
    """Build a client that sends requests to a fake handler instead of the API."""

    def build(handler: Handler) -> JobsucheClient:
        http = httpx.Client(
            base_url=str(api_config.base_url), transport=httpx.MockTransport(handler)
        )
        return JobsucheClient(api_config, http=http, sleep=sleeps.append)

    return build
