import pytest

from skillradar.api.postings import REFNR, marks, readable
from skillradar.skills.taxonomy import load_taxonomy


@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy()


def found(text, skills, taxonomy):
    return [(text[m["start"] : m["end"]], m["kind"]) for m in marks(text, skills, taxonomy)]


def test_skills_languages_and_home_office(taxonomy):
    text = "Sehr gute Python- und PySpark-Kenntnisse, Docker von Vorteil. Deutsch C1, Home-Office."
    assert found(text, [("Python", True), ("Spark", True), ("Docker", False)], taxonomy) == [
        ("Python", "required"),
        ("PySpark", "required"),
        ("Docker", "nice"),
        ("Deutsch", "language"),
        ("Home-Office", "home_office"),
    ]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Gute Deutschkenntnisse", [("Deutschkenntnisse", "language")]),
        ("fließend Englisch", [("Englisch", "language")]),
        ("Standort in Deutschland", []),
        ("Teams across Germany", []),
        ("mobiles Arbeiten möglich", [("mobiles Arbeiten", "home_office")]),
    ],
)
def test_language_and_home_office_words(taxonomy, text, expected):
    assert found(text, [], taxonomy) == expected


def test_marks_never_overlap(taxonomy):
    # "Data Warehouse" and "Warehouse" would overlap; the longer one wins.
    text = "Erfahrung mit Data-Warehouse und Data Warehouse Design"
    result = marks(text, [("Data Warehouse", True), ("Warehouse", False)], taxonomy)
    ends = [(m["start"], m["end"]) for m in result]
    assert all(a[1] <= b[0] for a, b in zip(ends, ends[1:], strict=False))
    assert [text[s:e] for s, e in ends] == ["Data-Warehouse", "Data Warehouse"]


def test_positions_fit_the_original_text(taxonomy):
    text = "Kenntnisse in REST‑APIs und Straße"  # a special dash and an ß
    [mark] = marks(text, [("REST", True)], taxonomy)
    assert text[mark["start"] : mark["end"]] == "REST‑APIs"


@pytest.mark.parametrize("refnr", ["13635-f28d5696_JB5265243-S", "10000-1207544109-S"])
def test_real_reference_numbers(refnr):
    assert REFNR.fullmatch(refnr)


@pytest.mark.parametrize("refnr", ["", "a", "../etc/passwd", "x' or 1=1", "a b", "x" * 81])
def test_bad_reference_numbers(refnr):
    assert not REFNR.fullmatch(refnr)


def test_readable_text():
    raw = (
        "### Dein Profil\n\n\n\n- **Abschluss:** Du hast&nbsp;ein Studium  \n"
        "* Python &amp; SQL\n**Wir bieten**"
    )
    assert readable(raw) == (
        "Dein Profil\n\n- Abschluss: Du hast ein Studium\n- Python & SQL\nWir bieten"
    )


def test_marks_fit_the_readable_text(taxonomy):
    text = readable("**Kenntnisse:** Python&nbsp;und SQL")
    assert found(text, [("Python", True), ("SQL", False)], taxonomy) == [
        ("Python", "required"),
        ("SQL", "nice"),
    ]
