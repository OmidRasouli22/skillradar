import pytest

from skillradar.extract.tables import (
    current_answers,
    language_rows,
    posting_rows,
    skill_rows,
    written_in,
)
from skillradar.skills.taxonomy import load_taxonomy


@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy()


def answer(refnr="a", version="v4", status="ok", at="2026-11-06T10:00:00", **output):
    base = {
        "role": "data_engineer",
        "seniority": "mid",
        "remote": "hybrid",
        "languages": [{"language": "German", "level": "fluent"}],
        "skills": [{"name": "Python", "required": True}],
    }
    return {
        "refnr": refnr,
        "model": "m",
        "prompt_version": version,
        "status": status,
        "extracted_at": at,
        "output": base | output if status == "ok" else None,
    }


class TestCurrentAnswers:
    def test_only_this_model_prompt_and_ok(self):
        results = [
            answer("a"),
            answer("b", version="v3"),
            answer("c", status="max_tokens"),
            answer("d") | {"model": "other"},
        ]
        assert [a["refnr"] for a in current_answers(results, "m", "v4")] == ["a"]

    def test_newest_answer_wins(self):
        old = answer(at="2026-11-01T00:00:00", seniority="junior")
        new = answer(at="2026-11-06T00:00:00", seniority="senior")
        [kept] = current_answers([new, old], "m", "v4")
        assert kept["output"]["seniority"] == "senior"


def test_posting_rows():
    [row] = posting_rows([answer()])
    assert row == {
        "refnr": "a",
        "role": "data_engineer",
        "seniority": "mid",
        "remote": "hybrid",
        "model": "m",
        "prompt_version": "v4",
        "extracted_at": "2026-11-06T10:00:00",
    }


def test_language_rows_have_one_row_per_language():
    languages = [
        {"language": "German", "level": "fluent"},
        {"language": "German", "level": "good"},
        {"language": "English", "level": "good"},
    ]
    rows = language_rows([answer(languages=languages)])
    assert rows == [
        {"refnr": "a", "language": "German", "level": "fluent"},
        {"refnr": "a", "language": "English", "level": "good"},
    ]


class TestSkillRows:
    def rows(self, taxonomy, skills, text):
        found = skill_rows([answer(skills=skills)], taxonomy, {"a": text})
        return {row["skill"]: row for row in found}

    def test_names_from_the_skill_list(self, taxonomy):
        rows = self.rows(taxonomy, [{"name": "PySpark", "required": True}], "PySpark")
        assert rows["Spark"]["category"] == "data" and rows["Spark"]["in_skill_list"]
        assert rows["Spark"]["general"] is False

    def test_emerging_skills(self, taxonomy):
        skills = [{"name": "GitHub Copilot", "required": False}, {"name": "Java", "required": True}]
        rows = self.rows(taxonomy, skills, "GitHub Copilot und Java")
        assert rows["GitHub Copilot"]["emerging"] is True and rows["Java"]["emerging"] is False

    def test_concepts_are_general(self, taxonomy):
        rows = self.rows(taxonomy, [{"name": "Networking", "required": True}], "Netzwerk")
        assert rows["Networking"]["general"] is True and rows["Networking"]["in_text"] is False

    def test_unknown_skill_keeps_its_name(self, taxonomy):
        rows = self.rows(taxonomy, [{"name": "Zemax  OpticStudio", "required": False}], "Zemax")
        row = rows["Zemax OpticStudio"]
        assert (row["category"], row["in_skill_list"], row["in_text"]) == (None, False, False)
        assert row["general"] is False

    def test_same_skill_twice_is_one_row(self, taxonomy):
        skills = [{"name": "Spark", "required": False}, {"name": "PySpark", "required": True}]
        rows = self.rows(taxonomy, skills, "Spark und PySpark")
        assert list(rows) == ["Spark"] and rows["Spark"]["required"] is True

    @pytest.mark.parametrize(
        "name, text, expected",
        [
            ("Spark", "Erfahrung mit PySpark", True),  # a spelling from the list
            ("REST", "REST‑Schnittstellen", True),  # a special dash
            ("AWS", "Erfahrung mit Cloud-Plattformen", False),  # model added a product
            ("Docker", "Container-Konzepte", False),
        ],
    )
    def test_in_text(self, taxonomy, name, text, expected):
        rows = self.rows(taxonomy, [{"name": name, "required": True}], text)
        assert rows[name]["in_text"] is expected

    def test_posting_without_text(self, taxonomy):
        rows = skill_rows([answer()], taxonomy, {})
        assert rows[0]["in_text"] is False


@pytest.mark.parametrize(
    "text, term, expected",
    [
        ("erfahrung mit java", "Java", True),
        ("erfahrung mit javascript", "Java", False),
        ("c++ und c#", "C", False),
        ("ci/cd-pipelines", "CI/CD", True),
        ("data-warehouse", "Data Warehouse", True),
        ("datawarehouse", "Data Warehouse", True),
        ("nothing", "", False),
    ],
)
def test_written_in(text, term, expected):
    assert written_in(text, term) is expected
