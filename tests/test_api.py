import duckdb
import pytest
from fastapi.testclient import TestClient

from skillradar.api.app import SECURITY_HEADERS, create_app
from skillradar.api.labels import REGIONS, ROLES
from skillradar.extract.schema import Role
from skillradar.transform.runner import serve_dir

SCOPE = [
    # refnr, role, region
    ("p1", "data_engineer", "BAYERN"),
    ("p2", "data_engineer", "BERLIN"),
    ("p3", "backend_developer", "BAYERN"),
    ("p4", "other_tech", "WIEN"),  # a place outside Germany: only in 'all'
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
            "('all', 'all', 'Python', 3, 2, 4, 0.75), ('all', 'all', 'SQL', 2, 2, 4, 0.5), "
            "('all', 'all', 'Rust', 2, 0, 4, 0.5), "
            "('data_engineer', 'all', 'SQL', 2, 2, 2, 1.0)"
            ") t(role, region, skill, postings, required_postings, total_postings, share)"
        )
        con.execute(
            "create table gold_meta as select date '2026-11-06' as as_of, 4 as tech_postings, "
            "'claude-haiku-5-5' as model, 'v4' as prompt_version"
        )
        for table in ("gold_scope", "gold_skill_demand", "gold_meta"):
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
        assert [s["name"] for s in data["skills"]] == ["Python", "Rust", "SQL"]
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
