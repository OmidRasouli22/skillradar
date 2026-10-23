from collections.abc import Callable

import httpx
import pytest

from skillradar.config import load_config
from skillradar.ingestion.client import JobsucheClient

Handler = Callable[[httpx.Request], httpx.Response]


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
