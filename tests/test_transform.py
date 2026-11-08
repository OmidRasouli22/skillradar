from datetime import date

import duckdb
import pytest

from skillradar.extract.postings import load_postings
from skillradar.extract.prompt import PROMPT_VERSION
from skillradar.extract.settings import load_settings
from skillradar.transform import cli
from skillradar.transform.runner import (
    TransformError,
    build,
    serve_dir,
    warehouse_path,
)
from tests.helpers import write_jsonl, write_run_log

DEFAULT_SKILLS = [{"name": "SQL", "required": True}, {"name": "AWS", "required": False}]


def llm_answer(refnr, prompt_version=PROMPT_VERSION, skills=None, role="data_engineer"):
    return {
        "refnr": refnr,
        "model": load_settings().model,
        "prompt_version": prompt_version,
        "status": "ok",
        "extracted_at": "2026-11-06T10:00:00",
        "output": {
            "role": role,
            "seniority": "mid",
            "remote": "hybrid",
            "languages": [{"language": "German", "level": "fluent"}],
            "skills": skills or DEFAULT_SKILLS,
        },
    }


def details(refnr, **fields):
    base = {
        "referenznummer": refnr,
        "stellenangebotsTitel": "Data Engineer (m/w/d)",
        "stellenangebotsart": "ARBEIT",
        "firma": "Müller GmbH",
        "datumErsteVeroeffentlichung": "2026-08-01",
        "aenderungsdatum": "2026-10-01T10:00:00.000",
        "stellenangebotsBeschreibung": "Wir suchen Erfahrung mit SQL und dbt.",
        "stellenlokationen": [{"adresse": {"ort": "Stuttgart"}, "breite": 48.7, "laenge": 9.1}],
    }
    return base | fields


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    day1 = data / "bronze/details/snapshot_date=2026-10-23"
    day2 = data / "bronze/details/snapshot_date=2026-10-24"
    run1, run2 = "20261023T060000Z", "20261024T060000Z"

    two_places = [
        {"adresse": {"ort": "Stuttgart", "plz": "70173", "region": "BADEN_WUERTTEMBERG"}},
        {"adresse": {"ort": "Esslingen"}, "breite": 48.74, "laenge": 9.31},
    ]
    contact = "Python, Kafka und LLMs. Fragen an Frau Anna Weber, Tel. 0711 123456, anna@firma.de"
    posting_a = details(
        "a",
        gehaltsspanneVon="55000",
        gehaltsspanneBis="70000.0",
        verguetungsangabe="JAHRESGEHALT",
        homeofficemoeglich=True,
        homeofficeprozent=40,
        stellenlokationen=two_places,
    )
    write_jsonl(
        day1 / f"run_{run1}.jsonl",
        [
            {"run_id": run1, "refnr": "a", "details": posting_a},
            {"run_id": run1, "refnr": "b", "details": details("b", stellenangebotsTitel="Old")},
            {"run_id": run1, "refnr": "gone", "details": None},
        ],
        tail='{"run_id": "x", "refnr": "cut-off',
    )
    newer_b = details(
        "b",
        stellenangebotsTitel="New",
        festgehalt="48000.0",
        stellenangebotsBeschreibung=contact,
        stellenlokationen=[{"adresse": {"ort": "Nürnberg, Mittelfranken"}}],
    )
    no_place = details("noplace", stellenlokationen=[])
    write_jsonl(
        day2 / f"run_{run2}.jsonl",
        [
            {"run_id": run2, "refnr": "b", "details": newer_b},
            {"run_id": run2, "refnr": "noplace", "details": no_place},
        ],
    )
    write_jsonl(day2 / "run_20261024T070000Z.jsonl.part", [{"run_id": "p", "refnr": "unfinished"}])
    write_run_log(data / "bronze", run2, status="ok", full_scope=True)
    search = data / f"bronze/search/snapshot_date=2026-10-24/run_{run2}.jsonl.gz"
    write_jsonl(
        search,
        [
            {"run_id": run2, "posting": {"referenznummer": "b"}},
            {"run_id": run2, "posting": {"referenznummer": "noplace"}},
        ],
    )

    # b is the only open posting. Its text names Python, Kafka and LLMs, not AWS or
    # "Networking".
    open_answer = llm_answer(
        "b",
        role="backend_developer",
        skills=[
            {"name": "Python", "required": True},
            {"name": "Kafka", "required": False},
            {"name": "AWS", "required": True},
            {"name": "Networking", "required": False},
            {"name": "LLM", "required": False},  # emerging, named as "LLMs"
        ],
    )
    answers = [
        llm_answer("a"),
        llm_answer("b", prompt_version="v0"),
        open_answer,
        llm_answer("noplace", role="not_tech"),  # open, but not a tech job
        llm_answer("not-a-posting"),
    ]
    write_jsonl(data / "llm/extractions/msgbatch_1.jsonl", answers)

    build(data)
    return data


def query(data_dir, sql):
    with duckdb.connect(str(warehouse_path(data_dir))) as con:
        return con.execute(sql).fetchall()


def postings(data_dir):
    with duckdb.connect(str(warehouse_path(data_dir))) as con:
        rows = con.execute("select * from silver_postings order by refnr")
        columns = [c[0] for c in rows.description]
        return {row[0]: dict(zip(columns, row, strict=True)) for row in rows.fetchall()}


class TestSilverPostings:
    def test_one_row_per_posting(self, data_dir):
        assert sorted(postings(data_dir)) == ["a", "b", "noplace"]

    def test_newest_record_wins(self, data_dir):
        b = postings(data_dir)["b"]
        assert b["title"] == "New"
        assert b["details_run_id"] == "20261024T060000Z"

    def test_fields(self, data_dir):
        a = postings(data_dir)["a"]
        assert a["employer"] == "Müller GmbH"
        assert a["first_published"] == date(2026, 8, 1)
        assert a["home_office"] is True
        assert a["home_office_percent"] == 40
        assert a["description_chars"] == len("Wir suchen Erfahrung mit SQL und dbt.")

    def test_raw_description_is_not_in_postings(self, data_dir):
        assert "description" not in postings(data_dir)["a"]

    def test_salary_range_and_fixed_salary(self, data_dir):
        rows = postings(data_dir)
        assert (rows["a"]["salary_min"], rows["a"]["salary_max"]) == (55000, 70000)
        assert (rows["b"]["salary_min"], rows["b"]["salary_max"]) == (48000, 48000)

    def test_missing_values_stay_unknown(self, data_dir):
        b = postings(data_dir)["b"]
        assert b["home_office"] is None
        assert b["pay_type"] is None


class TestSilverLocations:
    def test_one_row_per_place_in_order(self, data_dir):
        rows = query(
            data_dir,
            "select position, city, postal_code, latitude from silver_posting_locations "
            "where refnr = 'a' order by position",
        )
        assert rows == [(1, "Stuttgart", "70173", None), (2, "Esslingen", None, 48.74)]

    def test_posting_without_places(self, data_dir):
        sql = "select count(*) from silver_posting_locations where refnr = 'noplace'"
        rows = query(data_dir, sql)
        assert rows == [(0,)]


class TestSilverTexts:
    def test_contact_data_is_removed(self, data_dir):
        [(text, emails, phones, names)] = query(
            data_dir,
            "select description, emails, phones, names from silver_posting_texts where refnr = 'b'",
        )
        assert text == "Python, Kafka und LLMs. Fragen an Frau [name], Tel. [phone], [email]"
        assert (emails, phones, names) == (1, 1, 1)

    def test_clean_text_is_unchanged(self, data_dir):
        sql = "select description from silver_posting_texts where refnr = 'a'"
        assert query(data_dir, sql) == [("Wir suchen Erfahrung mit SQL und dbt.",)]

    def test_one_row_per_posting(self, data_dir):
        sql = "select refnr from silver_posting_texts order by refnr"
        assert query(data_dir, sql) == [("a",), ("b",), ("noplace",)]


class TestSkillTables:
    def test_only_current_prompt_and_known_postings(self, data_dir):
        sql = "select refnr, role from silver_posting_extractions order by refnr"
        assert query(data_dir, sql) == [
            ("a", "data_engineer"),
            ("b", "backend_developer"),
            ("noplace", "not_tech"),
        ]

    def test_skills_are_checked_against_the_text(self, data_dir):
        rows = query(
            data_dir,
            "select skill, required, in_skill_list, general, in_text "
            "from silver_posting_skills where refnr = 'a' order by skill",
        )
        # The text names SQL but not AWS.
        assert rows == [("AWS", False, True, False, False), ("SQL", True, True, False, True)]

    def test_languages(self, data_dir):
        assert query(data_dir, "select * from silver_posting_languages order by refnr") == [
            ("a", "German", "fluent"),
            ("b", "German", "fluent"),
            ("noplace", "German", "fluent"),
        ]


def test_gold_tables_are_exported_for_the_api(data_dir):
    folder = serve_dir(data_dir)
    names = sorted(path.name for path in folder.iterdir())
    assert names == [
        "gold_attribute_shares.parquet",
        "gold_emerging_share.parquet",
        "gold_meta.parquet",
        "gold_posting_skills.parquet",
        "gold_posting_texts.parquet",
        "gold_postings.parquet",
        "gold_scope.parquet",
        "gold_skill_demand.parquet",
        "gold_skill_weekly.parquet",
        "gold_weeks.parquet",
    ]
    assert folder.stat().st_mode & 0o777 == 0o700
    with duckdb.connect() as con:
        exported = len(con.read_parquet(str(folder / "gold_skill_demand.parquet")).fetchall())
    assert exported == query(data_dir, "select count(*) from gold_skill_demand")[0][0]


def test_postings_load_right_after_a_build(data_dir):
    # The daily job builds, then reads postings for Claude in the same process.
    postings = load_postings(warehouse_path(data_dir), only_open=True)
    assert [p.refnr for p in postings] == ["b", "noplace"]


class TestGoldTables:
    def test_scope_has_open_postings_per_role_and_region(self, data_dir):
        rows = query(data_dir, "select refnr, role, region from gold_scope order by role")
        # b is open and has no region, so it is only in 'all'. a is closed, and noplace is
        # open but not a tech job.
        assert rows == [("b", "all", "all"), ("b", "backend_developer", "all")]

    def test_skill_demand_leaves_out_made_up_products(self, data_dir):
        rows = query(
            data_dir,
            "select skill, postings, required_postings, total_postings, share "
            "from gold_skill_demand where role = 'all' and region = 'all' order by skill",
        )
        # AWS is not in the text, so it is left out. Networking is a concept, so it counts.
        assert rows == [
            ("Kafka", 1, 0, 1, 1.0),
            ("LLM", 1, 0, 1, 1.0),
            ("Networking", 1, 0, 1, 1.0),
            ("Python", 1, 1, 1, 1.0),
        ]

    def test_emerging_share(self, data_dir):
        rows = query(
            data_dir,
            "select role, region, postings, total_postings, share "
            "from gold_emerging_share order by role",
        )
        assert rows == [("all", "all", 1, 1, 1.0), ("backend_developer", "all", 1, 1, 1.0)]

    def test_postings_for_the_job_list(self, data_dir):
        rows = query(
            data_dir,
            "select refnr, title, role, seniority, remote, city, region, german, english "
            "from gold_postings",
        )
        assert rows == [
            ("b", "New", "backend_developer", "mid", "hybrid", "Nürnberg", None, "fluent",
             "not asked")
        ]  # fmt: skip
        skills = query(data_dir, "select skill, required from gold_posting_skills order by skill")
        # AWS is not in the text, so it is left out here too.
        assert skills == [("Kafka", False), ("LLM", False), ("Networking", False), ("Python", True)]
        [(text,)] = query(data_dir, "select description from gold_posting_texts")
        assert "[email]" in text and "Anna" not in text

    def test_attribute_shares(self, data_dir):
        rows = query(
            data_dir,
            "select attribute, value, share from gold_attribute_shares "
            "where role = 'all' and region = 'all' order by attribute",
        )
        assert rows == [
            ("english", "not asked", 1.0),
            ("german", "fluent", 1.0),
            ("remote", "hybrid", 1.0),
            ("seniority", "mid", 1.0),
        ]

    def test_meta(self, data_dir):
        [(as_of, open_postings, with_answers, tech, _, version)] = query(
            data_dir, "select * from gold_meta"
        )
        # Two open postings have an answer; only b is a tech job.
        assert (str(as_of), open_postings, with_answers, tech, version) == (
            "2026-10-24",
            2,
            2,
            1,
            PROMPT_VERSION,
        )


def test_city_names_are_cleaned(data_dir):
    sql = "select city, city_raw from silver_posting_locations where refnr = 'b'"
    assert query(data_dir, sql) == [("Nürnberg", "Nürnberg, Mittelfranken")]


def test_build_needs_bronze_files(tmp_path):
    with pytest.raises(TransformError, match="search"):
        build(tmp_path)


def test_build_needs_run_logs(tmp_path):
    write_jsonl(tmp_path / "bronze/search/snapshot_date=2026-10-23/run_1.jsonl.gz", [])
    write_jsonl(tmp_path / "bronze/details/snapshot_date=2026-10-23/run_1.jsonl", [])

    with pytest.raises(TransformError, match="runs"):
        build(tmp_path)


def test_quote_in_path_is_rejected(tmp_path):
    folder = tmp_path / "it's"
    folder.mkdir()

    with pytest.raises(TransformError, match="quote"):
        build(folder)


def test_cli_reports_errors(tmp_path, capsys):
    assert cli.main(["--data-dir", str(tmp_path)]) == 1
    assert "run skillradar-snapshot first" in capsys.readouterr().err
