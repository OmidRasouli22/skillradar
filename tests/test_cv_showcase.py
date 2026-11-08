"""The example CVs in showcase/cv: files valid, and Claude's saved reading passes its checks.

The profile checks run on profile.json, saved by `skillradar-cv showcase --refresh`, so
these tests need no API. The match checks need today's postings and run in that command.
"""

import json

import pytest

from skillradar.cv import showcase
from skillradar.cv.profile import CvProfile
from skillradar.skills.taxonomy import load_taxonomy

CASES = showcase.load_all(showcase.SHOWCASE_DIR)
TAXONOMY = load_taxonomy()


def test_the_examples_are_valid():
    assert len(CASES) >= 9
    assert showcase.validate_all(showcase.SHOWCASE_DIR) == []


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_every_example_has_a_saved_reading(case):
    assert case.profile is not None, "run skillradar-cv showcase --refresh"
    assert case.saved["prompt_version"] and case.saved["model"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_the_reading_passes_its_checks(case):
    failed = [
        (r.check.kind, r.actual, r.check.why) for r in showcase.check_profile(case) if not r.passed
    ]
    assert failed == []


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_checks_name_real_skills_and_targets(case):
    names = set(TAXONOMY.names())
    for check in case.file.checks:
        for skill in [*check.skills, *([check.skill] if check.skill else [])]:
            assert skill in names or skill.endswith("(fluent, C1)"), skill
    assert case.file.target.role != "not_tech"


def test_a_saved_profile_that_does_not_fit_is_reported(tmp_path):
    folder = tmp_path / "cv"
    (folder / "x1").mkdir(parents=True)
    (folder / "x1" / "cv.md").write_text("text")
    (folder / "x1" / "case.yaml").write_text(
        "title: T\nperson: P\nlanguage: English\ntarget: {role: data_engineer, region: all}\n"
        "story: S\nchecks:\n  - {kind: role, values: [data_engineer], why: a reason here}\n"
    )
    (folder / "x1" / "profile.json").write_text(json.dumps({"profile": {"role": "not_tech"}}))
    assert showcase.load(folder, "x1").profile is None
    assert "does not fit" in showcase.validate_all(folder)[0]
    assert showcase.load(folder, "../x1") is None


def test_match_checks_and_report():
    case = next(c for c in CASES if c.id == "backend-java-limited-german")
    analysis = {
        "role_label": "Backend Developer",
        "region_label": "All regions",
        "summary": {"scored": 10, "good_or_better": 3},
        "roles": [{"id": "backend_developer"}, {"id": "fullstack_developer"}],
        "demand": [{"skill": "Spring", "coverage": {"kind": "have", "via": None}}],
        "gaps": [{"name": "German (fluent, C1)", "gained": 4}, {"name": "Python", "gained": 1}],
    }
    results = showcase.check_match(case, analysis)
    assert results and all(r.passed for r in results)
    text = showcase.report([(case, results, analysis)], "2026-11-08")
    assert "| ✅ |" in text and "| ❌ |" not in text and case.file.title in text
    assert "German (fluent, C1) (+4)" in text


def test_a_failed_check_shows_in_the_report():
    case = next(c for c in CASES if c.id == "data-engineer-berlin")
    broken = case.profile.model_copy(update={"seniority": "lead"})
    other = showcase.Case(
        case.id, case.file, case.text, CvProfile.model_validate(broken.model_dump())
    )
    results = showcase.check_profile(other)
    failed = [r for r in results if not r.passed]
    assert [(r.check.kind, r.actual) for r in failed] == [("seniority", "lead")]
    assert "| ❌ |" in showcase.report([(other, results, None)], None)
