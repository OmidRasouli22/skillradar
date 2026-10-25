import duckdb
import pytest

from skillradar.skills import report
from skillradar.skills.taxonomy import load_taxonomy


@pytest.fixture
def data_dir(tmp_path):
    with duckdb.connect(str(tmp_path / "warehouse.duckdb")) as con:
        con.execute("create table silver_postings (refnr varchar, title varchar)")
        con.execute("create table silver_posting_texts (refnr varchar, description varchar)")
        con.execute(
            "insert into silver_postings values "
            "('a', 'Data Engineer (m/w/d)'), ('b', 'Backend Developer'), ('c', 'Koch')"
        )
        con.execute(
            "insert into silver_posting_texts values "
            "('a', 'SQL, Python und dbt'), ('b', 'Java und SQL'), ('c', 'Kochen mit Liebe')"
        )
    return tmp_path


def test_count_skills():
    counts = report.count_skills(
        ["Python, SQL", "SQL und Python und SQL", "nichts"], load_taxonomy()
    )
    assert counts == {"SQL": 2, "Python": 2}


def test_report(data_dir, capsys):
    assert report.main(["report", "--data-dir", str(data_dir)]) == 0

    out = capsys.readouterr().out
    assert "3 postings, 67% with at least one known skill" in out
    assert "SQL" in out and "66.7%" in out


def test_title_filter(data_dir, capsys):
    assert report.main(["report", "--data-dir", str(data_dir), "--title", "data engineer"]) == 0

    out = capsys.readouterr().out
    assert out.startswith("1 postings")
    assert "dbt" in out and "Java" not in out


def test_title_is_a_parameter_not_sql(data_dir, capsys):
    title = "x' or 1=1 --"
    assert report.main(["report", "--data-dir", str(data_dir), "--title", title]) == 1
    assert "no postings match" in capsys.readouterr().err


def test_missing_warehouse(tmp_path, capsys):
    assert report.main(["report", "--data-dir", str(tmp_path)]) == 1
    assert "run skillradar-transform first" in capsys.readouterr().err
