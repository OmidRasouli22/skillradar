import base64

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

from skillradar.api.app import create_app
from skillradar.cv import showcase
from tests.cv_helpers import CV_TEXT, FakeClient, make_pdf, message, write_market

LOCAL = "http://127.0.0.1:8000"
JSON = {"Content-Type": "application/json", "Origin": LOCAL}
PROFILE = {
    "role": "data_engineer",
    "seniority": "mid",
    "languages": [{"language": "German", "level": "native"}],
    "skills": [
        {"name": "SQL", "evidence": "work"},
        {"name": "Python", "evidence": "work"},
        {"name": "AWS", "evidence": "project"},
    ],
}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    write_market(tmp_path)
    fake = FakeClient()
    app = create_app(tmp_path, web_build=tmp_path / "no-page", make_client=lambda: fake)
    return TestClient(app, base_url=LOCAL), fake, tmp_path


def post(client, path, body, headers=JSON):
    return client.post(path, json=body, headers=headers)


def test_status(setup):
    client, _, _ = setup
    body = client.get("/api/cv/status").json()
    assert body["claude"] is True and body["model"] == "claude-haiku-5-5"
    assert 0 <= body["room_left_usd"] <= body["budget_usd"]
    assert body["limits"]["max_chars"] == 30_000 and "Python" in body["skills"]
    assert {"id": "BERLIN", "label": "Berlin"} in body["regions"]


def test_status_without_a_key(setup, monkeypatch):
    client, _, _ = setup
    monkeypatch.setattr("skillradar.api.cv.load_dotenv", lambda *_: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert client.get("/api/cv/status").json()["claude"] is False
    response = post(client, "/api/cv/read", {"text": CV_TEXT, "mode": "claude"})
    assert response.status_code == 503 and "quick read" in response.json()["detail"]


class TestPdf:
    def test_text(self, setup):
        client, _, _ = setup
        data = base64.b64encode(make_pdf([CV_TEXT])).decode()
        body = post(client, "/api/cv/pdf", {"data": data}).json()
        assert body["pages"] == 1 and "Airflow" in body["text"] and body["chars"] > 200

    @pytest.mark.parametrize(
        "data, detail",
        [
            ("not base64 at all!", "decoded"),
            (base64.b64encode(b"hello world, not a pdf").decode(), "not a PDF"),
        ],
    )
    def test_bad_files(self, setup, data, detail):
        client, _, _ = setup
        response = post(client, "/api/cv/pdf", {"data": data})
        assert response.status_code == 422 and detail in response.json()["detail"]

    def test_too_large_is_refused_before_decoding(self, setup):
        client, _, _ = setup
        response = post(client, "/api/cv/pdf", {"data": "A" * (7_000_000)})
        assert response.status_code == 422


class TestRead:
    def test_keywords(self, setup):
        client, fake, _ = setup
        body = post(client, "/api/cv/read", {"text": CV_TEXT, "mode": "keywords"}).json()
        assert body["mode"] == "keywords" and body["cost_usd"] == 0
        assert {"Python", "Airflow"} <= {s["name"] for s in body["profile"]["skills"]}
        assert fake.messages.sent == []

    def test_claude(self, setup):
        client, fake, data_dir = setup
        body = post(client, "/api/cv/read", {"text": CV_TEXT, "mode": "claude"}).json()
        assert body["profile"]["role"] == "data_engineer" and body["cost_usd"] > 0
        assert len(fake.messages.sent) == 1
        # Nothing of the CV is written to disk; only the usage for the budget.
        saved = "".join(
            p.read_text(errors="ignore") for p in data_dir.rglob("*") if p.suffix == ".jsonl"
        )
        assert "Example GmbH" not in saved and "Airflow" not in saved

    def test_short_text(self, setup):
        client, _, _ = setup
        response = post(client, "/api/cv/read", {"text": "Python", "mode": "keywords"})
        assert response.status_code == 422 and "too short" in response.json()["detail"]

    def test_over_budget(self, setup, monkeypatch):
        client, fake, _ = setup
        monkeypatch.setattr("skillradar.extract.budget.room_left", lambda *_: 0.0)
        response = post(client, "/api/cv/read", {"text": CV_TEXT, "mode": "claude"})
        assert response.status_code == 402 and fake.messages.sent == []

    @pytest.mark.parametrize(
        "error, status",
        [
            (
                anthropic.AuthenticationError(
                    "bad key",
                    response=httpx.Response(401, request=httpx.Request("POST", "http://x")),
                    body=None,
                ),
                502,
            ),
            (anthropic.APIConnectionError(request=httpx.Request("POST", "http://x")), 502),
        ],
    )
    def test_api_errors(self, setup, error, status):
        client, fake, _ = setup
        fake.messages.reply = error
        response = post(client, "/api/cv/read", {"text": CV_TEXT, "mode": "claude"})
        assert response.status_code == status
        assert response.json()["detail"] in (
            "the Claude API key was rejected",
            "Claude could not be reached; try again",
        )

    def test_refusal(self, setup):
        client, fake, _ = setup
        fake.messages.reply = message(stop_reason="refusal")
        response = post(client, "/api/cv/read", {"text": CV_TEXT, "mode": "claude"})
        assert response.status_code == 422 and "declined" in response.json()["detail"]


class TestAnalyse:
    def test_result(self, setup):
        client, _, _ = setup
        body = post(
            client,
            "/api/cv/analyse",
            {"profile": PROFILE, "role": "data_engineer", "region": "BERLIN"},
        ).json()
        assert body["summary"]["scored"] == 2 and body["region_label"] == "Berlin"
        assert [m["refnr"] for m in body["matches"]] == ["p1", "p2"]
        p1 = body["matches"][0]
        assert p1["band"] == "strong" and p1["match"] == pytest.approx(2 / 2.4, abs=1e-4)

    @pytest.mark.parametrize(
        "change",
        [
            {"role": "astronaut"},
            {"region": "MARS"},
            {"profile": {**PROFILE, "role": "not_tech"}},
            {"profile": {**PROFILE, "skills": [{"name": "", "evidence": "work"}]}},
            {"profile": {**PROFILE, "extra": 1}},
        ],
    )
    def test_bad_requests(self, setup, change):
        client, _, _ = setup
        body = {"profile": PROFILE, "role": "data_engineer", "region": "all"} | change
        assert post(client, "/api/cv/analyse", body).status_code == 422

    def test_no_data_yet(self, tmp_path):
        client = TestClient(create_app(tmp_path, web_build=tmp_path / "x"), base_url=LOCAL)
        response = post(
            client, "/api/cv/analyse", {"profile": PROFILE, "role": "all", "region": "all"}
        )
        assert response.status_code == 503


class TestShowcases:
    def test_list_and_detail(self, setup):
        client, _, _ = setup
        items = client.get("/api/cv/showcases").json()
        assert len(items) == len(showcase.load_all(showcase.SHOWCASE_DIR))
        detail = client.get(f"/api/cv/showcases/{items[0]['id']}").json()
        assert detail["text"] and detail["profile"]["skills"] and detail["checks"]

    def test_checks_run_live(self, setup):
        client, _, _ = setup
        body = client.get("/api/cv/showcases/data-engineer-berlin/checks").json()
        assert body["as_of"] == "2026-11-08"
        kinds = {r["kind"] for r in body["results"]}
        assert {"role", "has", "best_role", "no_gap"} <= kinds
        profile_checks = [r for r in body["results"] if r["kind"] in showcase.PROFILE_KINDS]
        assert all(r["passed"] for r in profile_checks)
        assert all(r["why"] and r["check"] for r in body["results"])

    @pytest.mark.parametrize("case_id, status", [("nope-x", 404), ("..%2F..", 404), ("A!", 422)])
    def test_unknown(self, setup, case_id, status):
        client, _, _ = setup
        assert client.get(f"/api/cv/showcases/{case_id}").status_code == status


class TestOnlyThisComputer:
    def test_other_host(self, setup):
        client, _, _ = setup
        response = client.get("/api/cv/status", headers={"Host": "evil.example"})
        assert response.status_code == 403

    def test_other_origin(self, setup):
        client, fake, _ = setup
        headers = {"Content-Type": "application/json", "Origin": "https://evil.example"}
        response = post(client, "/api/cv/read", {"text": CV_TEXT, "mode": "claude"}, headers)
        assert response.status_code == 403 and fake.messages.sent == []

    def test_form_posts_are_refused(self, setup):
        client, fake, _ = setup
        response = client.post(
            "/api/cv/read",
            content=f"text={CV_TEXT}&mode=claude",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Origin": LOCAL},
        )
        assert response.status_code == 415 and fake.messages.sent == []


def test_pages_answer_get_and_head(tmp_path):
    build = tmp_path / "out"
    build.mkdir()
    for name in ("index", "cv", "health"):
        (build / f"{name}.html").write_text(f"<p>{name}</p>")
    client = TestClient(create_app(tmp_path, web_build=build), base_url=LOCAL)
    for page in ("/cv", "/health"):
        assert client.get(page).status_code == 200
        assert client.head(page).status_code == 200
    assert "<p>cv</p>" in client.get("/cv").text
