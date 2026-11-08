import os

import pytest
from fastapi.testclient import TestClient

from skillradar.api.app import create_app
from skillradar.evaluate.labels import LabelStore, texts_path
from skillradar.storage import json_line

LOCAL = "http://127.0.0.1:8000"
JSON = {"Content-Type": "application/json", "Origin": LOCAL}

TEXT = "Wir suchen Erfahrung mit Python und SQL. Docker von Vorteil. Deutsch fließend."


def answer(skills=(("Python", True),)):
    return {
        "role": "data_engineer",
        "seniority": "mid",
        "remote": "unknown",
        "languages": [{"language": "German", "level": "fluent"}],
        "skills": [{"name": name, "required": req} for name, req in skills],
    }


@pytest.fixture
def setup(tmp_path):
    store = LabelStore(tmp_path / "labels.jsonl")
    store.create(["job-1", "job-2"])
    texts = texts_path(tmp_path)
    texts.parent.mkdir(parents=True)
    texts.write_text(json_line({"refnr": "job-1", "title": "Data Engineer", "text": TEXT}))
    app = create_app(tmp_path, web_build=tmp_path / "no-page", labels=store.path)
    return TestClient(app, base_url=LOCAL), store, texts


def test_sample_and_choices(setup):
    client, _, _ = setup
    body = client.get("/api/labels").json()
    assert [(i["refnr"], i["status"], i["title"]) for i in body["items"]] == [
        ("job-1", "todo", "Data Engineer"),
        ("job-2", "todo", None),
    ]
    assert {"id": "not_tech", "hint": "not IT, software or data work at all"} in body["choices"][
        "role"
    ]
    assert "German" in body["choices"]["language"] and "Python" in body["skills"]


def test_one_posting_without_claudes_answer(setup):
    client, _, _ = setup
    body = client.get("/api/labels/job-1").json()
    assert body["text"] == TEXT and body["label"]["status"] == "todo"
    assert set(body) == {"refnr", "title", "text", "label"}


@pytest.mark.parametrize(
    "path, status",
    [("/api/labels/job-2", 404), ("/api/labels/nope-9", 404), ("/api/labels/..", 404)],
)
def test_missing_postings(setup, path, status):
    client, _, _ = setup
    assert client.get(path).status_code == status


def test_bad_reference_number(setup):
    client, _, _ = setup
    assert client.get("/api/labels/a b").status_code == 422


def test_save_a_label(setup):
    client, store, _ = setup
    body = {"answer": answer(), "status": "verified", "note": "ok"}
    response = client.put("/api/labels/job-1", json=body, headers={"Origin": LOCAL})
    assert response.status_code == 200
    saved = store.get("job-1")
    assert saved.status == "verified" and saved.verified_at and saved.note == "ok"


@pytest.mark.parametrize(
    "body",
    [
        {"answer": answer(), "status": "todo"},
        {"answer": {**answer(), "role": "wizard"}, "status": "verified"},
        {"answer": answer(), "status": "verified", "extra": 1},
        {"answer": answer([(f"s{i}", True) for i in range(151)]), "status": "verified"},
    ],
)
def test_bad_labels_are_refused(setup, body):
    client, store, _ = setup
    assert client.put("/api/labels/job-1", json=body, headers=JSON).status_code == 422
    assert store.get("job-1").status == "todo"


def test_label_outside_the_sample(setup):
    client, _, _ = setup
    body = {"answer": answer(), "status": "verified"}
    assert client.put("/api/labels/other-1", json=body, headers=JSON).status_code == 404


def test_other_sites_cannot_write(setup):
    client, store, _ = setup
    body = {"answer": answer(), "status": "verified"}
    evil = {"Content-Type": "application/json", "Origin": "https://evil.example"}
    assert client.put("/api/labels/job-1", json=body, headers=evil).status_code == 403
    # A form or plain text can be sent cross-site without asking the server first.
    plain = {"Content-Type": "text/plain", "Origin": LOCAL}
    response = client.put("/api/labels/job-1", content=b'{"status": "verified"}', headers=plain)
    assert response.status_code == 415
    assert store.get("job-1").status == "todo"


@pytest.mark.parametrize("host", ["evil.example", "127.0.0.1.evil.example", ""])
def test_other_hosts_are_refused(setup, host):
    # A DNS rebinding attack reaches this server under another host name.
    client, _, _ = setup
    assert client.get("/api/labels", headers={"Host": host}).status_code == 403


def test_localhost_name_works(setup):
    client, _, _ = setup
    assert client.get("/api/labels", headers={"Host": "localhost:3000"}).status_code == 200


def test_marks_for_the_label(setup):
    client, _, _ = setup
    skills = [{"name": "Python", "required": True}, {"name": "Docker", "required": False}]
    response = client.post("/api/labels/job-1/marks", json={"skills": skills}, headers=JSON)
    marks = response.json()["marks"]
    found = {(TEXT[m["start"] : m["end"]], m["kind"]) for m in marks}
    assert {("Python", "required"), ("Docker", "nice"), ("Deutsch", "language")} <= found


def test_new_texts_are_read_again(setup):
    client, _, texts = setup
    texts.write_text(json_line({"refnr": "job-2", "title": "Analyst", "text": "Power BI"}))
    stat = texts.stat()
    os.utime(texts, (stat.st_atime, stat.st_mtime + 5))
    assert client.get("/api/labels/job-2").json()["text"] == "Power BI"


def test_review_page_is_served(tmp_path):
    page = tmp_path / "out"
    page.mkdir()
    (page / "index.html").write_text("start")
    (page / "label.html").write_text("review")
    client = TestClient(create_app(tmp_path, web_build=page, labels=tmp_path / "l.jsonl"))
    assert client.get("/label").text == "review"


def test_health_api_and_page(tmp_path):
    page = tmp_path / "out"
    page.mkdir()
    (page / "index.html").write_text("start")
    (page / "health.html").write_text("health page")
    client = TestClient(create_app(tmp_path, web_build=page, labels=tmp_path / "l.jsonl"))
    assert client.get("/health").text == "health page"
    body = client.get("/api/health").json()
    assert body["freshness"]["state"] == "stale" and body["runs"] == []
