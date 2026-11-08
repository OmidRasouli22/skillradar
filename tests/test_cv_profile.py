from datetime import date
from typing import get_args

import pytest
from pydantic import ValidationError

from skillradar.cv.profile import (
    CV_SCHEMA,
    AnswerJob,
    CvProfile,
    CvRole,
    CvSkill,
    experience_years,
    language_levels,
    language_name,
    merge_skills,
    strength,
)

TODAY = date(2026, 11, 8)


def job(start, end, kind="job", tech=True):
    return AnswerJob(start=start, end=end, kind=kind, tech=tech)


def test_schema_objects_are_closed_and_fully_required():
    def objects(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                yield node
            for value in node.values():
                yield from objects(value)
        elif isinstance(node, list):
            for value in node:
                yield from objects(value)

    found = list(objects(CV_SCHEMA))
    assert len(found) == 4  # profile, job, language, skill
    for obj in found:
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])


def test_a_cv_role_is_always_a_tech_role():
    assert "not_tech" not in get_args(CvRole)
    assert CV_SCHEMA["properties"]["role"]["enum"] == list(get_args(CvRole))
    with pytest.raises(ValidationError):
        CvProfile(role="not_tech", seniority="mid")


def test_language_names_are_free_text_in_the_answer():
    # A fixed list made Claude answer "Italian" for a Persian speaker.
    assert CV_SCHEMA["properties"]["languages"]["items"]["properties"]["language"] == {
        "type": "string"
    }


@pytest.mark.parametrize(
    "evidence, last_used, expected",
    [
        ("work", 2026, 1.0),
        ("project", None, 0.8),
        ("education", 2024, 0.7),
        ("listed", None, 0.6),
        ("work", 2021, 0.8),  # five years ago: counts a little less
        ("listed", 2015, 0.48),
    ],
)
def test_strength(evidence, last_used, expected):
    skill = CvSkill(name="Python", evidence=evidence, last_used=last_used)
    assert strength(skill, 2026) == pytest.approx(expected)


def test_merge_keeps_the_strongest_evidence_and_the_most_years():
    merged = merge_skills(
        [
            CvSkill(name="Python", evidence="listed", years=5, last_used=2020),
            CvSkill(name="python", evidence="work", years=2, last_used=2026),
            CvSkill(name="SQL", evidence="project"),
        ]
    )
    assert [(s.name.casefold(), s.evidence, s.years, s.last_used) for s in merged] == [
        ("python", "work", 5, 2026),
        ("sql", "project", None, None),
    ]


class TestExperienceYears:
    def test_jobs_until_today(self):
        jobs = [job("2022-06", "2024-04"), job("2024-05", "present")]
        assert experience_years(jobs, TODAY) == 4.5  # 54 months

    def test_overlapping_jobs_count_once(self):
        jobs = [job("2020-01", "2021-12"), job("2021-01", "2022-12")]
        assert experience_years(jobs, TODAY) == 3.0

    def test_only_tech_jobs_and_freelance_count(self):
        jobs = [
            job("2023-01", "2023-12"),
            job("2020-01", "2020-12", kind="freelance"),
            job("2018-01", "2018-12", kind="working_student"),
            job("2017-01", "2017-12", kind="internship"),
            job("2015-08", "2018-07", kind="apprenticeship"),
            job("2010-01", "2014-12", tech=False),
        ]
        assert experience_years(jobs, TODAY) == 2.0

    def test_a_year_alone_is_the_whole_year(self):
        assert experience_years([job("2019", "2020")], TODAY) == 2.0

    def test_german_words_for_now_and_other_separators(self):
        jobs = [job("2025/11", "heute"), job("2024.01", "2024.06")]
        assert experience_years(jobs, TODAY) == 1.6  # 13 + 6 months

    def test_no_dates_is_unknown_but_no_tech_jobs_is_zero(self):
        assert experience_years([job(None, None)], TODAY) is None
        assert experience_years([], TODAY) is None
        assert experience_years([job("2018-01", "present", tech=False)], TODAY) == 0.0

    @pytest.mark.parametrize(
        "start, end",
        [
            ("2027-01", "present"),
            ("2020-13", "2021-01"),
            ("soon", "present"),
            ("2022-05", "2021-01"),
        ],
    )
    def test_impossible_dates_are_left_out(self, start, end):
        assert experience_years([job(start, end), job("2025-11", "2026-10")], TODAY) == 1.0

    def test_a_future_end_stops_today(self):
        assert experience_years([job("2026-01", "2026-12")], TODAY) == pytest.approx(0.9)


@pytest.mark.parametrize(
    "text, name",
    [
        ("German", "German"),
        ("deutsch", "German"),
        ("Englisch", "English"),
        ("Chinese (Mandarin)", "Chinese"),
        ("Türkisch", "Turkish"),
        ("Persian", "Other"),
        ("", "Other"),
    ],
)
def test_language_name(text, name):
    assert language_name(text) == name


def test_language_levels_keep_the_higher_level():
    profile = CvProfile(
        role="data_engineer",
        seniority="mid",
        languages=[
            {"language": "German", "level": "good"},
            {"language": "German", "level": "fluent"},
            {"language": "English", "level": "unknown"},
        ],
    )
    assert language_levels(profile) == {"German": "fluent", "English": "unknown"}


@pytest.mark.parametrize(
    "field, value",
    [("years", -1), ("years", 61), ("last_used", 1960), ("name", ""), ("context", "x" * 161)],
)
def test_edited_skills_are_checked(field, value):
    with pytest.raises(ValidationError):
        CvSkill(**{"name": "Python", "evidence": "work", field: value})


def test_a_profile_takes_at_most_150_skills():
    skills = [{"name": f"Skill {i}", "evidence": "listed"} for i in range(151)]
    with pytest.raises(ValidationError):
        CvProfile(role="data_engineer", seniority="mid", skills=skills)
