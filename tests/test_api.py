import duckdb
import pytest
from fastapi.testclient import TestClient

from skillradar.api.app import SECURITY_HEADERS, create_app
from skillradar.api.data import TABLES
from skillradar.api.labels import REGIONS, ROLES
from skillradar.extract.schema import Role
from skillradar.transform.runner import serve_dir

SCOPE = [
    # refnr, role, region
    ("job-1", "data_engineer", "BAYERN"),
    ("job-2", "data_engineer", "BERLIN"),
    ("job-3", "backend_developer", "BAYERN"),
    ("job-4", "other_tech", "WIEN"),  # a place outside Germany: only in 'all'
]


def write_gold(data_dir):
    rows = []
    for refnr, role, region in SCOPE:
        for r in (role, "all"):
            for g in {region, "all"} if region in REGIONS else {"all"}:
                rows.append((refnr, r, g))
    folder = serve_dir(data_dir)
    folder.mkdir(parents=True)
    with duckdb.connect() as con:
        con.execute("create table gold_scope (refnr varchar, role varchar, region varchar)")
        con.executemany("insert into gold_scope values (?, ?, ?)", rows)
        con.execute(
            "create table gold_skill_demand as select * from (values "
            "('all', 'all', 'Python', false, 3, 2, 4, 0.75), "
            "('all', 'all', 'SQL', false, 2, 2, 4, 0.5), "
            "('all', 'all', 'Rust', false, 2, 0, 4, 0.5), "
            "('all', 'all', 'RAG', true, 1, 0, 4, 0.25), "
            "('data_engineer', 'all', 'SQL', false, 2, 2, 2, 1.0)"
            ") t(role, region, skill, emerging, postings, required_postings, total_postings, share)"
        )
        con.execute(
            "create table gold_attribute_shares as select * from (values "
            "('all', 'all', 'german', 'fluent', 3, 4, 0.75), "
            "('all', 'all', 'german', 'not asked', 1, 4, 0.25), "
            "('all', 'all', 'remote', 'hybrid', 4, 4, 1.0)"
            ") t(role, region, attribute, value, postings, total_postings, share)"
        )
        con.execute(
            "create table gold_emerging_share as select * from (values "
            "('all', 'all', 1, 4, 0.25), ('data_engineer', 'all', 0, 2, 0.0)"
            ") t(role, region, postings, total_postings, share)"
        )
        con.execute(
            "create table gold_postings as select * from (values "
            "('job-1', 'Data Engineer (m/w/d)', 'Acme', date '2026-11-05', 'data_engineer', "
            "'mid', 'hybrid', 'München', 'BAYERN', 'fluent', 'not asked'), "
            "('job-2', 'Senior Data Engineer', 'Beta', date '2026-11-06', 'data_engineer', "
            "'senior', 'remote', 'Berlin', 'BERLIN', 'not asked', 'good'), "
            "('job-3', 'Backend Developer', 'Gamma', null, 'backend_developer', "
            "'junior', 'onsite', 'Nürnberg', 'BAYERN', 'good', 'not asked'), "
            "('job-4', 'Developer', 'Delta', date '2026-11-01', 'other_tech', "
            "'mid', 'unknown', 'Wien', 'WIEN', 'not asked', 'not asked')"
            ") t(refnr, title, employer, first_published, role, seniority, remote, city, "
            "region, german, english)"
        )
        con.execute(
            "create table gold_posting_skills as select * from (values "
            "('job-1', 'SQL', true, false), ('job-1', 'Python', false, false), "
            "('job-1', 'RAG', false, true)"
            ") t(refnr, skill, required, emerging)"
        )
        con.execute(
            "create table gold_posting_texts as select * from (values "
            "('job-1', 'Sehr gute SQL-Kenntnisse, Python von Vorteil. Deutsch C1. Home-Office.'),"
            "('job-2', 'Text'), ('job-3', 'Text'), ('job-4', 'Text')"
            ") t(refnr, description)"
        )
        con.execute(
            "create table gold_meta as select date '2026-11-06' as as_of, 4 as tech_postings, "
            "'claude-haiku-5-5' as model, 'v4' as prompt_version"
        )
        for table in TABLES:
            con.execute(f"copy {table} to '{folder / table}.parquet' (format parquet)")


@pytest.fixture
def client(tmp_path):
    write_gold(tmp_path)
    return TestClient(create_app(tmp_path, web_build=tmp_path / "no-page"))


def test_every_role_has_a_label():
    from typing import get_args

    assert set(ROLES) == set(get_args(Role)) - {"not_tech"} | {"all"}


class TestOverview:
    def test_meta_roles_and_regions(self, client):
        data = client.get("/api/overview").json()
        assert data["as_of"] == "2026-11-06" and data["tech_postings"] == 4
        assert [r["id"] for r in data["roles"]] == [
            "all",
            "data_engineer",
            "backend_developer",
            "other_tech",  # always last
        ]
        assert data["roles"][1] == {"id": "data_engineer", "label": "Data Engineer", "postings": 2}

    def test_places_outside_germany_are_not_offered(self, client):
        regions = client.get("/api/overview").json()["regions"]
        assert [r["id"] for r in regions] == ["all", "BAYERN", "BERLIN"]
        assert regions[0]["postings"] == 4


class TestSkills:
    def test_all_roles_and_regions(self, client):
        data = client.get("/api/skills").json()
        assert data["total_postings"] == 4
        # Most postings first; ties by name.
        assert [s["name"] for s in data["skills"]] == ["Python", "Rust", "SQL", "RAG"]
        assert data["skills"][0] == {
            "name": "Python",
            "postings": 3,
            "required_postings": 2,
            "share": 0.75,
            "required_share": 0.5,
        }

    def test_one_role(self, client):
        data = client.get("/api/skills", params={"role": "data_engineer"}).json()
        assert data["total_postings"] == 2 and [s["name"] for s in data["skills"]] == ["SQL"]

    def test_limit(self, client):
        assert len(client.get("/api/skills", params={"limit": 1}).json()["skills"]) == 1

    def test_group_without_postings(self, client):
        data = client.get("/api/skills", params={"role": "mobile_developer"}).json()
        assert data["total_postings"] == 0 and data["skills"] == []

    @pytest.mark.parametrize(
        "params",
        [
            {"role": "astronaut"},
            {"region": "WIEN"},
            {"region": "x' or 1=1 --"},
            {"limit": 0},
            {"limit": 51},
            {"limit": "many"},
        ],
    )
    def test_bad_input_is_rejected(self, client, params):
        assert client.get("/api/skills", params=params).status_code == 422


class TestDashboard:
    def test_everything_for_one_region(self, client):
        data = client.get("/api/dashboard").json()
        assert data["region"] == "all" and data["total_postings"] == 4
        assert data["as_of"] == "2026-11-06" and data["model"] == "claude-haiku-5-5"
        assert [r["id"] for r in data["roles"]][0] == "all"
        assert [s["name"] for s in data["skills"]["all"]] == ["Python", "Rust", "SQL", "RAG"]
        assert data["skills"]["data_engineer"][0]["required_share"] == 1.0

    def test_heatmap_has_zero_where_a_role_never_asks(self, client):
        heatmap = client.get("/api/dashboard").json()["heatmap"]
        assert heatmap["skills"] == ["Python", "Rust", "SQL", "RAG"]
        rows = {row["id"]: row["shares"] for row in heatmap["rows"]}
        assert "all" not in rows
        assert rows["data_engineer"] == [0.0, 0.0, 1.0, 0.0]
        assert rows["backend_developer"] == [0.0, 0.0, 0.0, 0.0]

    def test_emerging(self, client):
        data = client.get("/api/dashboard").json()
        assert data["emerging_skills"] == [{"name": "RAG", "postings": 1, "share": 0.25}]
        assert data["emerging"]["all"] == {"postings": 1, "share": 0.25}

    def test_attributes(self, client):
        german = client.get("/api/dashboard").json()["attributes"]["all"]["german"]
        assert german == [
            {"value": "fluent", "postings": 3, "share": 0.75},
            {"value": "not asked", "postings": 1, "share": 0.25},
        ]

    def test_states_leave_out_places_outside_germany(self, client):
        states = client.get("/api/dashboard").json()["states"]
        assert sorted(s["id"] for s in states["all"]) == ["BAYERN", "BERLIN"]
        assert "other_tech" not in states  # its only place is in Austria

    def test_one_region(self, client):
        data = client.get("/api/dashboard", params={"region": "BERLIN"}).json()
        assert data["total_postings"] == 1 and data["skills"] == {}

    @pytest.mark.parametrize("region", ["WIEN", "nowhere", "x' or 1=1 --"])
    def test_unknown_region(self, client, region):
        assert client.get("/api/dashboard", params={"region": region}).status_code == 422


class TestPostings:
    def test_list_for_a_role_newest_first(self, client):
        data = client.get("/api/postings", params={"role": "data_engineer"}).json()
        assert data["total"] == 2
        assert [p["refnr"] for p in data["items"]] == ["job-2", "job-1"]
        # Required skills first on the card.
        assert data["items"][1]["skills"] == ["SQL", "Python", "RAG"]
        assert data["items"][0]["published"] == "2026-11-06"

    def test_list_for_a_region_and_paging(self, client):
        data = client.get("/api/postings", params={"region": "BAYERN", "limit": 1}).json()
        assert data["total"] == 2 and len(data["items"]) == 1
        page_two = client.get(
            "/api/postings", params={"region": "BAYERN", "limit": 1, "offset": 1}
        ).json()
        assert page_two["items"][0]["refnr"] != data["items"][0]["refnr"]

    def test_one_posting_with_marks(self, client):
        data = client.get("/api/postings/job-1").json()
        assert data["title"] == "Data Engineer (m/w/d)" and data["role"] == "Data Engineer"
        assert data["region"] == "Bayern" and data["german"] == "fluent"
        assert data["url"] == "https://www.arbeitsagentur.de/jobsuche/jobdetail/job-1"
        assert data["role_id"] == "data_engineer" and data["role_postings"] == 2
        # SQL is in 100% of the fixture's data_engineer postings; Python has no role row.
        assert data["skills"][0] == {
            "name": "SQL",
            "required": True,
            "emerging": False,
            "share_in_role": 1.0,
        }
        assert data["skills"][1]["share_in_role"] == 0.0
        marked = [(data["text"][m["start"] : m["end"]], m["kind"]) for m in data["marks"]]
        assert marked == [
            ("SQL", "required"),
            ("Python", "nice"),
            ("Deutsch", "language"),
            ("Home-Office", "home_office"),
        ]

    def test_unknown_posting(self, client):
        assert client.get("/api/postings/job-999").status_code == 404

    @pytest.mark.parametrize("refnr", ["x' or 1=1", "a"])
    def test_bad_reference_number(self, client, refnr):
        assert client.get(f"/api/postings/{refnr}").status_code == 422

    @pytest.mark.parametrize(
        "params", [{"role": "astronaut"}, {"region": "WIEN"}, {"offset": -1}, {"limit": 51}]
    )
    def test_bad_list_input(self, client, params):
        assert client.get("/api/postings", params=params).status_code == 422


def test_no_data_yet(tmp_path):
    client = TestClient(create_app(tmp_path, web_build=tmp_path / "no-page"))
    response = client.get("/api/overview")
    assert response.status_code == 503 and "skillradar-transform" in response.json()["detail"]


def test_security_headers(client):
    response = client.get("/api/overview")
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value


def test_page_not_built_yet(client):
    response = client.get("/")
    assert response.status_code == 200 and "npm run build" in response.text


def test_built_page_is_served(tmp_path):
    write_gold(tmp_path)
    page = tmp_path / "out"
    page.mkdir()
    (page / "index.html").write_text("<h1>SkillRadar</h1>")
    client = TestClient(create_app(tmp_path, web_build=page))
    assert client.get("/").text == "<h1>SkillRadar</h1>"
    assert client.get("/api/overview").status_code == 200
