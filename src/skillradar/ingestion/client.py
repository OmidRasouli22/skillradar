"""Client for the Jobsuche API of the Bundesagentur für Arbeit."""

import base64
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx

from skillradar.config import ApiConfig
from skillradar.ingestion.models import Posting, SearchPage

SEARCH_PATH = "/pc/v6/jobs"
DETAILS_PATH = "/pc/v4/jobdetails/{key}"
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


class JobsucheError(Exception):
    """Request failed and retrying will not help."""


def encode_refnr(refnr: str) -> str:
    """The details endpoint expects the refnr as base64."""
    return base64.b64encode(refnr.encode()).decode()


class JobsucheClient:
    def __init__(
        self,
        config: ApiConfig,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._owns_http = http is None
        self._http = http or httpx.Client(
            base_url=str(config.base_url), timeout=config.timeout_seconds
        )
        self._http.headers["X-API-Key"] = config.api_key
        self._sleep = sleep
        self._sent_first_request = False

    def __enter__(self) -> "JobsucheClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def search_page(self, term: str, city: str, radius_km: int, page: int) -> SearchPage:
        params = {
            "was": term,
            "wo": city,
            "umkreis": radius_km,
            "page": page,
            "size": self._config.page_size,
        }
        response = self._get(SEARCH_PATH, params=params)
        return SearchPage.model_validate(response.json())

    def search(self, term: str, city: str, radius_km: int) -> Iterator[Posting]:
        """Yield all postings for a search, page by page."""
        page = 1
        while True:
            result = self.search_page(term, city, radius_km, page)
            yield from result.postings
            if not result.postings or page * self._config.page_size >= result.total:
                return
            page += 1

    def details(self, refnr: str) -> Posting | None:
        """Full posting with description, or None if it is gone."""
        response = self._get(DETAILS_PATH.format(key=encode_refnr(refnr)), not_found_ok=True)
        return None if response is None else response.json()

    def _get(
        self, path: str, params: dict[str, Any] | None = None, not_found_ok: bool = False
    ) -> httpx.Response | None:
        retries = self._config.max_retries
        for attempt in range(retries + 1):
            self._wait_between_requests()
            try:
                response = self._http.get(path, params=params)
            except httpx.TransportError as error:
                if attempt == retries:
                    raise JobsucheError(f"network error for {path}: {error}") from error
                self._backoff(attempt)
                continue

            if response.status_code in RETRY_STATUS_CODES and attempt < retries:
                self._backoff(attempt)
                continue
            if response.status_code == 404 and not_found_ok:
                return None
            if response.status_code == 403:
                raise JobsucheError(f"403 for {path}: this network may be blocked by the API")
            if response.is_error:
                raise JobsucheError(f"{response.status_code} for {path}")
            return response

        raise AssertionError("unreachable")

    def _wait_between_requests(self) -> None:
        if self._sent_first_request:
            self._sleep(self._config.request_delay_seconds)
        self._sent_first_request = True

    def _backoff(self, attempt: int) -> None:
        self._sleep(2**attempt)
