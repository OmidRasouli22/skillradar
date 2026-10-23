import httpx
import pytest

from skillradar.ingestion.client import JobsucheError, encode_refnr
from tests.helpers import load_fixture

REFNR = "10001-1003252000-S"


def search_response(refnrs: list[str], total: int) -> httpx.Response:
    posting = load_fixture("search_posting.json")
    postings = [{**posting, "referenznummer": refnr} for refnr in refnrs]
    return httpx.Response(200, json={"ergebnisliste": postings, "maxErgebnisse": total})


def test_search_page_sends_expected_request(make_client):
    requests = []

    def handler(request):
        requests.append(request)
        return search_response([REFNR], total=1)

    page = make_client(handler).search_page("Data Engineer", "Stuttgart", 25, page=1)

    request = requests[0]
    assert request.url.path.endswith("/jobsuche-service/pc/v6/jobs")
    assert request.url.params["was"] == "Data Engineer"
    assert request.url.params["wo"] == "Stuttgart"
    assert request.url.params["umkreis"] == "25"
    assert request.url.params["page"] == "1"
    assert request.headers["X-API-Key"] == "jobboerse-jobsuche"
    assert page.total == 1
    assert page.postings[0]["referenznummer"] == REFNR


def test_search_reads_all_pages(make_client, api_config):
    size = api_config.page_size
    total = 2 * size + 5

    def handler(request):
        page = int(request.url.params["page"])
        count = size if page <= 2 else 5
        return search_response([f"{page}-{i}" for i in range(count)], total=total)

    postings = list(make_client(handler).search("Python", "Berlin", 25))

    assert len(postings) == total


def test_search_stops_on_empty_page(make_client):
    pages = []

    def handler(request):
        pages.append(request.url.params["page"])
        return search_response([], total=500)

    assert list(make_client(handler).search("Python", "Berlin", 25)) == []
    assert pages == ["1"]


def test_details_uses_base64_refnr(make_client):
    def handler(request):
        assert request.url.path.endswith(f"/pc/v4/jobdetails/{encode_refnr(REFNR)}")
        return httpx.Response(200, json=load_fixture("job_details.json"))

    details = make_client(handler).details(REFNR)

    assert details["referenznummer"] == REFNR
    assert details["stellenangebotsBeschreibung"]


def test_details_returns_none_when_posting_is_gone(make_client):
    client = make_client(lambda request: httpx.Response(404))

    assert client.details(REFNR) is None


def test_retries_server_errors_then_succeeds(make_client, sleeps):
    responses = iter([httpx.Response(503), httpx.Response(503), search_response([REFNR], 1)])
    client = make_client(lambda request: next(responses))

    page = client.search_page("Java", "Hamburg", 25, page=1)

    assert page.total == 1
    assert 1 in sleeps and 2 in sleeps


def test_gives_up_after_max_retries(make_client, api_config):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500)

    with pytest.raises(JobsucheError, match="500"):
        make_client(handler).search_page("Java", "Hamburg", 25, page=1)
    assert len(calls) == api_config.max_retries + 1


def test_retries_network_errors(make_client):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("connection reset")
        return search_response([REFNR], 1)

    assert make_client(handler).search_page("Java", "Hamburg", 25, page=1).total == 1


def test_forbidden_fails_without_retry(make_client):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(403)

    with pytest.raises(JobsucheError, match="403"):
        make_client(handler).search_page("Java", "Hamburg", 25, page=1)
    assert len(calls) == 1


def test_waits_between_requests(make_client, api_config, sleeps):
    client = make_client(lambda request: search_response([REFNR], 1))

    client.search_page("Java", "Hamburg", 25, page=1)
    client.search_page("Java", "Hamburg", 25, page=2)

    assert sleeps == [api_config.request_delay_seconds]
