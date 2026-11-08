import pytest

from skillradar.cv.families import SkillFamilies, load_families
from skillradar.cv.match import (
    GOOD,
    MIN_SKILLS,
    Credits,
    analyse,
    band,
    language_fit,
    score,
    seniority_fit,
)
from skillradar.cv.profile import CvProfile, CvSkill
from skillradar.skills.taxonomy import load_taxonomy
from tests.cv_helpers import market, posting

TAXONOMY = load_taxonomy()
FAMILIES = load_families(TAXONOMY)
YEAR = 2026


def profile(*skills, seniority="mid", languages=(("German", "native"), ("English", "fluent"))):
    """skills: (name, evidence) pairs or names (used at work)."""
    return CvProfile(
        role="data_engineer",
        seniority=seniority,
        languages=[{"language": lang, "level": level} for lang, level in languages],
        skills=[
            CvSkill(name=s, evidence="work")
            if isinstance(s, str)
            else CvSkill(name=s[0], evidence=s[1])
            for s in skills
        ],
    )


def credits(person, postings=(), families=FAMILIES):
    return Credits(person, families, market(list(postings)).similarity, YEAR, TAXONOMY)


class TestCredits:
    def test_have_by_evidence_and_any_spelling(self):
        c = credits(profile("Python", ("SQL", "listed"), "Golang"))
        assert c.of("python").kind == "have" and c.of("Python").value == 1.0
        assert c.of("SQL").value == 0.6
        assert c.of("Go").kind == "have"  # Golang is a spelling of Go
        assert c.of("Rust").kind == "missing" and c.of("Rust").value == 0

    def test_a_product_proves_a_concept(self):
        c = credits(profile(("AWS", "project"), "PostgreSQL"))
        cloud = c.of("Cloud Computing")
        assert (cloud.kind, cloud.via, cloud.value) == ("proven", "AWS", 0.8)
        assert c.of("SQL").kind == "proven" and c.of("SQL").via == "PostgreSQL"

    def test_the_stronger_source_wins(self):
        c = credits(profile(("JavaScript", "listed"), "TypeScript"))
        js = c.of("JavaScript")
        assert (js.kind, js.via, js.value) == ("proven", "TypeScript", 1.0)

    def test_a_substitute_counts_partly_and_by_likeness(self):
        jobs = [posting(f"a{i}", ["AWS", "Terraform", "Kubernetes"]) for i in range(3)]
        jobs += [posting(f"z{i}", ["Azure", "Terraform", "Kubernetes"]) for i in range(3)]
        jobs += [posting(f"x{i}", ["Excel", "SAP"]) for i in range(3)]
        c = credits(profile("AWS"), jobs)
        azure = c.of("Azure")
        assert azure.kind == "substitute" and azure.via == "AWS"
        assert 0 < azure.value <= 0.5
        likeness = market(jobs).similarity.of("Azure", "AWS")
        assert azure.value == pytest.approx(0.5 * likeness, abs=1e-4)

    def test_a_rare_substitute_gets_the_default_likeness(self):
        c = credits(profile(("React", "project")))
        angular = c.of("Angular")
        assert angular.kind == "substitute" and angular.value == pytest.approx(0.5 * 0.6 * 0.8)

    def test_skills_that_only_appear_together_give_no_credit(self):
        c = credits(profile("Python", "Docker"))
        assert c.of("SQL").kind == "missing" and c.of("Kubernetes").kind == "missing"

    def test_without_families_only_own_skills_count(self):
        c = credits(profile("AWS"), families=SkillFamilies())
        assert c.of("Azure").kind == "missing" and c.of("Cloud Computing").kind == "missing"


@pytest.mark.parametrize(
    "needed, have, fit",
    [
        ("not asked", None, 1.0),
        ("fluent", "native", 1.0),
        ("fluent", "fluent", 1.0),
        ("fluent", "good", 0.7),
        ("fluent", "basic", 0.4),
        ("fluent", None, 0.4),
        ("unknown", "good", 1.0),  # asked without a level reads as good
        ("unknown", "basic", 0.7),
        ("good", "unknown", 1.0),  # named without a level reads as good
        ("native", "fluent", 0.7),
    ],
)
def test_language_fit(needed, have, fit):
    assert language_fit(needed, have) == fit


@pytest.mark.parametrize(
    "posting_level, person, fit",
    [
        ("mid", "mid", 1.0),
        ("senior", "mid", 0.8),
        ("lead", "mid", 0.5),
        ("junior", "mid", 0.9),
        ("junior", "lead", 0.7),
        ("student", "student", 1.0),
        ("student", "senior", 0.5),
        ("junior", "student", 0.85),
        ("mid", "student", 0.6),
        ("senior", "student", 0.3),
        ("unknown", "junior", 1.0),
        ("senior", "unknown", 1.0),
    ],
)
def test_seniority_fit(posting_level, person, fit):
    assert seniority_fit(posting_level, person) == fit


def test_bands():
    assert [band(v) for v in (0.95, 0.7, 0.69, 0.5, 0.3, 0.29, 0)] == [
        "strong", "strong", "good", "good", "partial", "weak", "weak",
    ]  # fmt: skip


def test_score_weighs_required_skills_more():
    # Required SQL and Python (1 each), nice Airflow (0.4): has SQL at work, Python listed.
    job = posting("p", ["SQL", "Python", "Airflow?"], german="fluent", seniority="senior")
    person = profile("SQL", ("Python", "listed"), languages=[("German", "good")])
    s = score(job, credits(person), {"German": "good"}, "mid")
    assert s.skills == pytest.approx((1 * 1.0 + 1 * 0.6 + 0.4 * 0) / 2.4)
    assert (s.language, s.seniority) == (0.7, 0.8)
    assert s.match == pytest.approx(s.skills * 0.7 * 0.8)


def test_language_fits_multiply():
    job = posting("p", ["SQL", "Python", "Airflow"], german="fluent", english="fluent")
    s = score(job, credits(profile("SQL")), {"German": "good"}, "mid")
    assert s.language == pytest.approx(0.7 * 0.4)


class TestAnalyse:
    def jobs(self):
        return [
            posting("de1", ["SQL", "Python", "Airflow"], published="2026-11-05"),
            posting("de2", ["SQL", "Python", "Spark"], published="2026-11-06"),
            posting("de3", ["SQL", "Spark", "Kafka", "Airflow?"], german="fluent"),
            posting("de4", ["SQL", "Spark", "Databricks"], regions=("BAYERN",)),
            posting("tiny", ["SQL", "Python"]),  # too few skills to score
            posting("be1", ["Java", "Spring", "SQL"], role="backend_developer"),
            posting("no", ["Excel", "SAP", "Word"], role="not_tech"),
        ]

    def run(self, person, role="data_engineer", region="BERLIN", jobs=None):
        return analyse(person, market(jobs or self.jobs()), FAMILIES, role, region, YEAR, TAXONOMY)

    def test_summary(self):
        result = self.run(profile("SQL", "Python", "Airflow"))
        s = result["summary"]
        assert MIN_SKILLS == 3
        assert (s["postings"], s["scored"]) == (4, 3)  # tiny is counted, not scored
        # de1 covered fully (1.0), de2 2/3, de3 (1 + 0.4) / 3.4
        assert s["good_or_better"] == 2
        assert s["bands"] == {"strong": 1, "good": 1, "partial": 1, "weak": 0}
        assert result["region_label"] == "Berlin" and result["as_of"] == "2026-11-08"

    def test_region_and_role_filters(self):
        everywhere = self.run(profile("SQL"), region="all")
        assert everywhere["summary"]["scored"] == 4  # de4 in Bayern counts too
        backend = self.run(profile("SQL"), role="backend_developer", region="all")
        assert [m["refnr"] for m in backend["matches"]] == ["be1"]
        anything = self.run(profile("SQL"), role="all", region="all")
        assert "no" not in {m["refnr"] for m in anything["matches"]}  # not tech work

    def test_best_matches_first_then_newest(self):
        result = self.run(profile("SQL", "Python", "Airflow"))
        assert [m["refnr"] for m in result["matches"]] == ["de1", "de2", "de3"]
        top = result["matches"][0]
        assert top["band"] == "strong" and top["parts"] == {
            "skills": 1.0,
            "language": 1.0,
            "seniority": 1.0,
        }
        de3 = result["matches"][2]
        assert de3["languages"] == [{"language": "German", "needed": "fluent", "have": "native"}]
        assert [s["skill"] for s in de3["skills"]] == ["Kafka", "Spark", "SQL", "Airflow"]

    def test_demand_shows_how_each_skill_is_covered(self):
        result = self.run(profile("SQL", ("Python", "listed")))
        rows = {r["skill"]: r for r in result["demand"]}
        assert rows["SQL"]["postings"] == 3 and rows["SQL"]["share"] == 1.0
        assert rows["Spark"]["required_postings"] == 2
        assert (
            rows["Python"]["coverage"]["kind"] == "have" and rows["Python"]["evidence"] == "listed"
        )
        assert rows["Kafka"]["coverage"]["kind"] == "missing" and rows["Kafka"]["evidence"] is None

    GAP_JOBS = [
        posting("g1", ["SQL", "Python", "Spark"]),
        posting("g2", ["SQL", "Spark", "Kafka"]),
        posting("g3", ["SQL", "Spark", "Airflow"]),
        posting("g4", ["SQL", "Python", "Kafka"]),
    ]

    def test_gaps_rank_by_postings_that_become_good(self):
        # Has SQL and Python: g1 and g4 are 2/3, already good; g2 and g3 are 1/3.
        # Learning Spark (0.8) lifts g2 and g3 to (1 + 0.8) / 3 = 0.6: two more good.
        # Kafka (2 postings) and Airflow (1) are asked too rarely to suggest.
        result = self.run(profile("SQL", "Python"), jobs=self.GAP_JOBS)
        [spark] = result["gaps"]
        assert (spark["name"], spark["kind"], spark["gained"], spark["postings"]) == (
            "Spark",
            "skill",
            2,
            3,
        )
        assert spark["mean_gain"] == pytest.approx((0.8 / 3) * 3 / 4, abs=1e-4)

    def test_never_suggest_what_one_has(self):
        result = self.run(profile("SQL", "Python", ("Spark", "listed")), jobs=self.GAP_JOBS)
        assert "Spark" not in [g["name"] for g in result["gaps"]]

    def test_gap_math_matches_a_full_rescore(self):
        before = self.run(profile("SQL"), jobs=self.GAP_JOBS)
        after = self.run(profile("SQL", ("Spark", "project")), jobs=self.GAP_JOBS)
        spark = next(g for g in before["gaps"] if g["name"] == "Spark")
        gained = after["summary"]["good_or_better"] - before["summary"]["good_or_better"]
        assert spark["gained"] == gained == 3
        total_before = sum(m["match"] for m in before["matches"])
        total_after = sum(m["match"] for m in after["matches"])
        assert spark["mean_gain"] == pytest.approx((total_after - total_before) / 4, abs=1e-3)

    def test_a_proven_skill_is_not_a_gap_but_a_substitute_is(self):
        jobs = [posting(f"j{i}", ["Azure", "Cloud Computing", "Terraform"]) for i in range(4)]
        result = self.run(profile("AWS", "Terraform"), jobs=jobs)
        names = [g["name"] for g in result["gaps"]]
        assert "Cloud Computing" not in names
        azure = next(g for g in result["gaps"] if g["name"] == "Azure")
        assert azure["coverage"]["kind"] == "substitute" and azure["coverage"]["via"] == "AWS"

    def test_language_gap(self):
        jobs = [
            posting("g1", ["SQL", "Python", "Spark"], german="fluent"),
            posting("g2", ["SQL", "Python", "Kafka"], german="fluent"),
            posting("g3", ["SQL", "Python", "Airflow"]),
        ]
        person = profile("SQL", "Python", "Spark", "Kafka", languages=[("German", "basic")])
        result = self.run(person, jobs=jobs)
        german = next(g for g in result["gaps"] if g["kind"] == "language")
        # Both German postings are fully covered on skills but cut to 0.4 by the language.
        assert german["name"] == "German (fluent, C1)" and german["gained"] == 2
        assert german["postings"] == 2 and german["coverage"] == {
            "kind": "lower",
            "via": "basic",
            "value": 0.0,
        }
        assert result["gaps"][0] == german

    def test_no_language_gap_when_fluent(self):
        result = self.run(profile("SQL"))
        assert not [g for g in result["gaps"] if g["kind"] == "language"]

    def test_role_fit(self):
        jobs = self.jobs() + [posting("be2", ["Java", "Spring", "Kafka"], role="backend_developer")]
        result = self.run(profile("Java", "Spring", "Kafka"), region="all", jobs=jobs)
        roles = result["roles"]
        # be1 2/3 and be2 3/3 are good; the data engineer postings are not.
        assert roles[0]["id"] == "backend_developer" and roles[0]["share"] == 1.0
        assert roles[0]["good_or_better"] == 2 and roles[0]["scored"] == 2
        assert roles[1]["id"] == "data_engineer" and roles[1]["share"] == 0.0
        assert {r["id"] for r in roles} == {"backend_developer", "data_engineer"}

    def test_builds_on_names_related_known_skills(self):
        jobs = [posting(f"s{i}", ["SQL", "Python", "Spark", "Airflow"]) for i in range(5)]
        jobs += [posting(f"e{i}", ["Excel", "SAP", "Word"], role="other_tech") for i in range(5)]
        result = self.run(profile("SQL", "Python"), region="all", jobs=jobs)
        spark = next(g for g in result["gaps"] if g["name"] == "Spark")
        assert set(spark["builds_on"]) <= {"SQL", "Python"} and spark["builds_on"]

    def test_no_postings(self):
        result = self.run(profile("SQL"), region="HAMBURG")
        assert result["summary"]["scored"] == 0 and result["summary"]["median"] is None
        assert result["gaps"] == [] and result["matches"] == [] and result["demand"] == []

    def test_good_threshold_is_the_gap_target(self):
        assert GOOD == 0.5
