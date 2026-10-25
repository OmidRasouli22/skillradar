import time

import pytest
from pydantic import ValidationError

from skillradar.skills.taxonomy import Taxonomy, key, load_taxonomy


@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy()


def tiny(skills):
    return Taxonomy.model_validate({"categories": {"language": "Languages"}, "skills": skills})


class TestSkillList:
    def test_loads(self, taxonomy):
        assert len(taxonomy.skills) > 150
        assert "dbt" in taxonomy.names()

    def test_names_are_unique(self, taxonomy):
        assert len(set(taxonomy.names())) == len(taxonomy.names())

    def test_every_category_is_used(self, taxonomy):
        used = {skill.category for skill in taxonomy.skills}
        assert used == set(taxonomy.categories)

    def test_ambiguous_skills_have_a_safe_spelling_or_none(self, taxonomy):
        for skill in taxonomy.skills:
            if skill.ambiguous:
                assert skill.name not in skill.search_terms()


class TestValidation:
    def test_same_alias_for_two_skills(self):
        with pytest.raises(ValidationError, match="used by"):
            tiny(
                [
                    {"name": "Python", "category": "language", "aliases": ["Py"]},
                    {"name": "PyPy", "category": "language", "aliases": ["py"]},
                ]
            )

    def test_unknown_category(self):
        with pytest.raises(ValidationError, match="unknown category"):
            tiny([{"name": "Python", "category": "snake"}])

    def test_empty_list(self):
        with pytest.raises(ValidationError):
            tiny([])


class TestNormalize:
    @pytest.mark.parametrize(
        "raw, name",
        [
            ("PySpark", "Spark"),
            ("apache spark", "Spark"),
            ("K8s", "Kubernetes"),
            ("Postgres", "PostgreSQL"),
            ("MS SQL", "SQL Server"),
            ("T-SQL", "SQL Server"),
            ("nodejs", "Node.js"),
            ("REST-API", "REST"),
            ("Golang", "Go"),
            ("c#", "C#"),
            ("C++", "C++"),
            ("Apache-Airflow", "Airflow"),
            ("  Spring   Boot ", "Spring"),
            ("GitHub", "Git"),
        ],
    )
    def test_spellings(self, taxonomy, raw, name):
        assert taxonomy.normalize(raw) == name

    @pytest.mark.parametrize("raw", ["", "unknown tool", "Javaa"])
    def test_unknown(self, taxonomy, raw):
        assert taxonomy.normalize(raw) is None

    def test_key(self):
        assert key("  Apache-Spark_SQL ") == "apache spark sql"


class TestFindInText:
    def find(self, taxonomy, text):
        return taxonomy.find_in_text(text)

    def test_german_posting(self, taxonomy):
        text = "Python-Kenntnisse, Erfahrung mit Apache Spark, dbt und Azure Data Factory."
        assert self.find(taxonomy, text) == {"Python", "Spark", "dbt", "Azure Data Factory"}

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("JavaScript", {"JavaScript"}),
            ("Java und JavaScript", {"Java", "JavaScript"}),
            ("C#/.NET", {"C#", ".NET"}),
            ("C++ und C#", {"C++", "C#"}),
            ("GitHub und Git", {"Git"}),
            ("Spring Boot", {"Spring"}),
            ("CI/CD-Pipelines", {"CI/CD"}),
            ("RESTful und REST-API und RESTAPI", {"REST"}),
        ],
    )
    def test_names_inside_other_names(self, taxonomy, text, expected):
        assert self.find(taxonomy, text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "Den Rest der Woche arbeitest du remote.",
            "Begleitung beim Go-Live",
            "Vitamin C und ein Obstkorb",
            "Ein Container-Terminal in Hamburg",
            "Corporate Identity (CI) und CD",
            "Im Frühling (spring) starten wir",
            "Wir bieten Sicherheit (safe) und Hive-Mind",
        ],
    )
    def test_normal_words_are_not_skills(self, taxonomy, text):
        assert self.find(taxonomy, text) == set()

    def test_ambiguous_skill_found_by_safe_alias(self, taxonomy):
        assert self.find(taxonomy, "Backend in Golang, Analysen in RStudio") == {"Go", "R"}

    def test_empty(self, taxonomy):
        assert self.find(taxonomy, "") == set()

    def test_long_text_is_fast(self, taxonomy):
        text = "Python, SQL und ein langer Satz ohne Inhalt. " * 5000
        start = time.perf_counter()
        assert self.find(taxonomy, text) == {"Python", "SQL"}
        assert time.perf_counter() - start < 2


def test_category_of(taxonomy):
    assert taxonomy.category_of("Kafka") == "data"
    assert taxonomy.category_of("nope") is None
