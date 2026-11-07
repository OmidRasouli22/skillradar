import json

import pytest
from pydantic import ValidationError

from skillradar.evaluate import cli
from skillradar.evaluate.labels import (
    Answer,
    Label,
    LabelError,
    LabelStore,
    draw_sample,
    texts_path,
)
from skillradar.evaluate.metrics import (
    SetCounts,
    accuracy_scores,
    bootstrap,
    compare_sets,
    f1,
    precision,
    recall,
)
from skillradar.evaluate.report import build_report
from skillradar.extract.batch import PostingText
from skillradar.extract.prompt import PROMPT_VERSION
from skillradar.extract.settings import load_settings
from skillradar.skills.taxonomy import load_taxonomy
from skillradar.storage import json_line

MODEL = load_settings().model


@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy()


def answer(skills=(), role="data_engineer", seniority="mid", remote="hybrid", languages=()):
    return Answer.model_validate(
        {
            "role": role,
            "seniority": seniority,
            "remote": remote,
            "languages": [{"language": lang, "level": level} for lang, level in languages],
            "skills": [{"name": name, "required": req} for name, req in skills],
        }
    )


def record(refnr, ans, model=MODEL, prompt_version=PROMPT_VERSION, status="ok"):
    return {
        "refnr": refnr,
        "model": model,
        "prompt_version": prompt_version,
        "status": status,
        "extracted_at": "2026-11-07T10:00:00",
        "output": ans.model_dump(),
    }


# --- metrics -------------------------------------------------------------------------


def test_set_counts():
    assert compare_sets({"a", "b", "c"}, {"b", "c", "d"}) == SetCounts(tp=2, fp=1, fn=1)


def test_micro_scores_add_up_all_postings():
    counts = [SetCounts(tp=3, fp=1, fn=0), SetCounts(tp=1, fp=0, fn=3)]
    assert precision(counts) == 4 / 5
    assert recall(counts) == 4 / 7
    assert f1(counts) == pytest.approx(2 * (4 / 5) * (4 / 7) / (4 / 5 + 4 / 7))


def test_scores_without_anything_to_score():
    nothing = [SetCounts(tp=0, fp=0, fn=0)]
    assert precision(nothing) is None
    assert recall(nothing) is None
    assert f1(nothing) is None


def test_bootstrap_is_repeatable_and_holds_the_value():
    hits = [True] * 70 + [False] * 30
    share = lambda items: sum(items) / len(items)  # noqa: E731
    first = bootstrap(hits, share)
    assert first == bootstrap(hits, share)
    low, high = first
    assert low < 0.7 < high
    assert 0.55 < low and high < 0.85  # about ±9 points for n = 100


def test_bootstrap_edge_cases():
    assert bootstrap([], lambda items: 1.0) is None
    assert bootstrap([True] * 10, lambda items: sum(items) / len(items)) == (1.0, 1.0)


def test_accuracy_lists_the_common_mistakes():
    pairs = [("mid", "mid"), ("mid", "senior"), ("mid", "senior"), ("junior", "mid")]
    result = accuracy_scores(pairs)
    assert result["n"] == 4
    assert result["accuracy"]["value"] == 0.25
    assert result["mistakes"][0] == {"correct": "mid", "predicted": "senior", "count": 2}


# --- labels --------------------------------------------------------------------------


def test_sample_is_repeatable():
    refnrs = {f"r{i}" for i in range(50)}
    assert draw_sample(refnrs, 10, seed=1) == draw_sample(refnrs, 10, seed=1)
    assert draw_sample(refnrs, 10, seed=1) != draw_sample(refnrs, 10, seed=2)
    assert len(set(draw_sample(refnrs, 10, seed=1))) == 10
    with pytest.raises(LabelError):
        draw_sample(refnrs, 51, seed=1)
    with pytest.raises(LabelError):
        draw_sample(refnrs, 0, seed=1)


def test_store_keeps_order_and_never_overwrites_a_sample(tmp_path):
    store = LabelStore(tmp_path / "labels.jsonl")
    store.create(["b", "a", "c"])
    assert [label.refnr for label in store.load()] == ["b", "a", "c"]
    assert all(label.status == "todo" for label in store.load())
    assert store.path.stat().st_mode & 0o777 == 0o644
    with pytest.raises(LabelError):
        store.create(["x"])


def test_drafts_only_fill_todo_labels(tmp_path):
    store = LabelStore(tmp_path / "labels.jsonl")
    store.create(["a", "b"])
    store.save("b", answer([("SQL", True)]), "verified")

    saved = store.add_drafts({"a": answer([("Python", True)]), "b": answer()}, by="model-x")
    assert saved == 1
    a, b = store.load()
    assert (a.status, a.drafted_by, a.answer.skills[0].name) == ("draft", "model-x", "Python")
    assert b.status == "verified" and b.answer.skills[0].name == "SQL"

    with pytest.raises(LabelError, match="not in the sample"):
        store.add_drafts({"zzz": answer()}, by="model-x")


def test_saving_a_label(tmp_path):
    store = LabelStore(tmp_path / "labels.jsonl")
    store.create(["a"])
    label = store.save("a", answer([("dbt", False)]), "verified", note="checked")
    assert label.status == "verified" and label.verified_at and label.note == "checked"
    assert store.get("a") == label
    # Back to draft: no longer counts as verified.
    assert store.save("a", answer(), "draft").verified_at is None
    with pytest.raises(LabelError):
        store.save("a", answer(), "todo")
    with pytest.raises(LabelError):
        store.save("nope", answer(), "verified")


def test_labels_are_checked():
    with pytest.raises(ValidationError):
        answer([(f"skill {i}", True) for i in range(151)])
    with pytest.raises(ValidationError):
        answer(role="wizard")
    with pytest.raises(ValidationError):
        Label.model_validate({"refnr": "a", "status": "todo", "extra": 1})


# --- report --------------------------------------------------------------------------

TEXTS = {
    "p1": PostingText("p1", "Data Engineer", "Wir erwarten SQL, Python und K8s. dbt von Vorteil."),
    "p2": PostingText("p2", "Data Analyst", "Power BI und SQL. Erfahrung als Scrum Master."),
}


def labels():
    return [
        Label(
            refnr="p1",
            status="verified",
            answer=answer(
                [("SQL", True), ("Python", True), ("K8s", True), ("dbt", False)],
                languages=[("German", "fluent")],
            ),
        ),
        Label(
            refnr="p2",
            status="verified",
            answer=answer(
                [("Power BI", True), ("SQL", True), ("Scrum Master", False)],
                role="data_analyst",
                seniority="junior",
            ),
        ),
    ]


def claude_results():
    return [
        # Kubernetes matches the label's "K8s"; Snowflake is not in the text.
        record(
            "p1",
            answer(
                [("SQL", True), ("Python", False), ("Kubernetes", True), ("Snowflake", True)],
                languages=[("German", "good")],
            ),
        ),
        # Missed SQL; "scrum master" matches "Scrum Master" despite the case.
        record(
            "p2",
            answer([("Power BI", True), ("scrum master", False)], role="data_analyst"),
        ),
        record("p1", answer([("SQL", True)]), prompt_version="v0"),
    ]


@pytest.fixture(scope="module")
def report(taxonomy):
    return build_report(labels(), TEXTS, claude_results(), taxonomy, MODEL, PROMPT_VERSION)


def system(report, suffix):
    return next(s for s in report["systems"] if s["id"].endswith(suffix))


def counts(scores):
    return scores["tp"], scores["fp"], scores["fn"]


def test_claude_raw_answers(report):
    raw = system(report, f"/{PROMPT_VERSION}")
    assert raw["postings"] == 2
    # Listed skills. p1: SQL, Python, Kubernetes right, Snowflake extra, dbt missed.
    # p2: Power BI right, SQL missed.
    assert counts(raw["skills"]) == (4, 1, 2)
    assert raw["skills"]["precision"]["value"] == round(4 / 5, 4)
    assert raw["skills"]["recall"]["value"] == round(4 / 6, 4)
    # All skills: "scrum master" also matches "Scrum Master", whatever the case.
    assert counts(raw["all_skills"]) == (5, 1, 2)


def test_counted_answers_drop_made_up_products(report):
    counted = system(report, "/counted")
    assert counts(counted["skills"]) == (4, 0, 2)
    assert counts(counted["all_skills"]) == (5, 0, 2)


def test_keyword_baseline(report):
    keywords = system(report, "keywords")
    # p1: SQL, Python, Kubernetes (from "K8s") and dbt. p2: Power BI and SQL, and "Scrum"
    # instead of "Scrum Master", which is not in the skill list.
    assert counts(keywords["skills"]) == (6, 1, 0)
    assert counts(keywords["all_skills"]) == (6, 1, 1)
    assert keywords["role"] is None and keywords["required"] is None


def test_fields_required_and_languages(report):
    counted = system(report, "/counted")
    assert counted["role"]["accuracy"]["value"] == 1.0
    assert counted["seniority"]["accuracy"]["value"] == 0.5
    assert counted["seniority"]["mistakes"] == [
        {"correct": "junior", "predicted": "mid", "count": 1}
    ]
    # Both sides found: SQL, Python, Kubernetes, Power BI, Scrum Master. Python is wrong.
    required = counted["required"]
    assert required["n"] == 5
    assert required["accuracy"]["value"] == 0.8
    assert (required["required_as_nice"], required["nice_as_required"]) == (1, 0)
    assert counted["languages"]["tp"] == 1
    assert counted["language_level"]["accuracy"]["value"] == 0.0


def test_older_prompt_versions_are_scored_on_their_postings(report):
    old = system(report, "/v0")
    assert old["postings"] == 1
    assert counts(old["skills"]) == (1, 0, 3)


def test_per_skill_rows(taxonomy):
    # SQL is labeled in all four postings and found in three; Kafka is named twice only.
    sql = [("SQL", True)]
    labels = [
        Label(refnr=r, status="verified", answer=answer(sql + extra))
        for r, extra in [("a", []), ("b", []), ("c", []), ("d", [("Kafka", True)])]
    ]
    texts = {r: PostingText(r, "Data Engineer", "SQL, Kafka") for r in "abcd"}
    found = [record(r, answer(sql)) for r in "abc"] + [record("d", answer([("Kafka", True)]))]
    report = build_report(labels, texts, found, taxonomy, MODEL, PROMPT_VERSION)
    rows = {row["skill"]: row for row in report["skills"]}
    assert rows["SQL"] == {
        "skill": "SQL",
        "in_skill_list": True,
        "labeled": 4,
        "predicted": 3,
        "tp": 3,
        "fp": 0,
        "fn": 1,
        "precision": 1.0,
        "recall": 0.75,
    }
    assert "Kafka" not in rows  # fewer than three mentions


def test_report_holds_no_posting_text(report):
    dumped = json.dumps(report)
    assert "Wir erwarten" not in dumped and "Erfahrung als" not in dumped


# --- command line --------------------------------------------------------------------


@pytest.fixture
def fake_data(monkeypatch, tmp_path):
    results = claude_results()
    monkeypatch.setattr(cli, "_texts_by_refnr", lambda data_dir: TEXTS)
    monkeypatch.setattr(
        cli, "_current", lambda data_dir: [r for r in results if r["prompt_version"] != "v0"]
    )
    monkeypatch.setattr(cli.ExtractionStore, "results", lambda self: results)
    return tmp_path


def run(fake_data, *args):
    labels_file = fake_data / "eval" / "labels.jsonl"
    return cli.main(["--data-dir", str(fake_data), "--labels", str(labels_file), *args])


def test_command_line_from_sample_to_report(fake_data, capsys):
    assert run(fake_data, "sample", "--size", "2") == 0
    assert run(fake_data, "sample", "--size", "2") == 1  # never replaces a sample
    capsys.readouterr()

    # The sample comes with the texts for the review page.
    texts_file = texts_path(fake_data)
    texts = [json.loads(line) for line in texts_file.read_text().splitlines()]
    assert {t["refnr"] for t in texts} == {"p1", "p2"}
    assert set(texts[0]) == {"refnr", "title", "text"}  # no hints from Claude
    assert texts_file.stat().st_mode & 0o777 == 0o600

    assert run(fake_data, "report") == 1  # nothing verified yet
    drafts = fake_data / "drafts.jsonl"
    drafts.write_text(
        "".join(
            json_line({"refnr": label.refnr, "answer": label.answer.model_dump()})
            for label in labels()
        )
    )
    assert run(fake_data, "drafts", str(drafts), "--by", "test-model") == 0
    assert run(fake_data, "report") == 1  # drafts don't count by default
    assert run(fake_data, "report", "--drafts") == 0
    out = capsys.readouterr().out
    assert "UNCHECKED" in out and "Keyword search" in out

    saved = json.loads((fake_data / "eval" / "report.json").read_text())
    assert saved["includes_drafts"] is True
    assert saved["sample"] == {"size": 2, "todo": 0, "draft": 2, "verified": 0}

    assert run(fake_data, "status") == 0
    assert "0 verified, 2 draft, 0 todo" in capsys.readouterr().out

    todo_file = fake_data / "todo.jsonl"
    assert run(fake_data, "texts", "--out", str(todo_file), "--todo") == 0
    assert todo_file.read_text() == ""  # every posting has a draft now


def test_bad_drafts_are_rejected(fake_data, capsys):
    run(fake_data, "sample", "--size", "1")
    bad = fake_data / "bad.jsonl"
    bad.write_text(json_line({"refnr": "p1", "answer": {"role": "wizard"}}))
    assert run(fake_data, "drafts", str(bad), "--by", "x") == 1
