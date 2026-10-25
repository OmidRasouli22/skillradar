from datetime import date

import duckdb
import pytest

from skillradar.transform import cli
from skillradar.transform.runner import TransformError, build, warehouse_path
from tests.helpers import write_jsonl, write_run_log


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
    contact = "Python und Kafka. Fragen an Frau Anna Weber, Tel. 0711 123456, anna@firma.de"
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
    write_jsonl(search, [{"run_id": run2, "posting": {"referenznummer": "b"}}])

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
        assert text == "Python und Kafka. Fragen an Frau [name], Tel. [phone], [email]"
        assert (emails, phones, names) == (1, 1, 1)

    def test_clean_text_is_unchanged(self, data_dir):
        sql = "select description from silver_posting_texts where refnr = 'a'"
        assert query(data_dir, sql) == [("Wir suchen Erfahrung mit SQL und dbt.",)]

    def test_one_row_per_posting(self, data_dir):
        sql = "select refnr from silver_posting_texts order by refnr"
        assert query(data_dir, sql) == [("a",), ("b",), ("noplace",)]


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
