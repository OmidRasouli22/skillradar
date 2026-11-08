"""Compare the extraction with the labels and write the numbers.

Systems compared on the same labeled postings:
- keywords: the skill list's keyword search (skills only, the baseline to beat)
- claude: Claude's answers to the current prompt, every skill it named
- claude as counted: the same answers after the site's rule that drops product names the
  posting does not contain; these are the skills the numbers on the site use
Answers to older prompt versions are scored too, on the labeled postings they cover.

Skill names on both sides go through config/skills.yaml, so "K8s" and "Kubernetes" match.
Skills are scored twice:
- skills: only skills in the skill list. Names match reliably, and these are the skills
  the site's charts are about. This is the main number.
- all_skills: every skill. A skill outside the list matches only by its exact name, so
  "OIDC" and "OpenID Connect" count as two different skills: a lower bound.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from skillradar.evaluate.labels import Label
from skillradar.evaluate.metrics import (
    SetCounts,
    accuracy,
    accuracy_scores,
    bootstrap,
    compare_sets,
    precision,
    recall,
    scored,
    set_scores,
)
from skillradar.extract.batch import PostingText
from skillradar.extract.tables import current_answers, skill_rows
from skillradar.skills.taxonomy import Taxonomy
from skillradar.storage import Record

FIELDS = ("role", "seniority", "remote")
# A skill needs this many labeled or predicted mentions to get its own row.
MIN_SKILL_MENTIONS = 3


@dataclass
class Prediction:
    # Skills are keyed by the case-folded name; names holds the name to show.
    skills: dict[str, bool | None]  # key -> required (None: not known)
    names: dict[str, str]  # key -> skill name
    fields: dict[str, str] = field(default_factory=dict)  # role, seniority, remote
    languages: dict[str, str] = field(default_factory=dict)  # language -> level

    @classmethod
    def of(cls, skills: Iterable[tuple[str, bool | None]], **rest) -> "Prediction":
        """From (name, required) pairs; a skill named twice is required if either says so."""
        required: dict[str, bool | None] = {}
        names: dict[str, str] = {}
        for name, flag in skills:
            key = name.casefold()
            names.setdefault(key, name)
            old = required.get(key)
            required[key] = flag if old is None else (old or bool(flag))
        return cls(skills=required, names=names, **rest)


def build_report(
    labels: list[Label],
    texts: dict[str, PostingText],
    results: list[Record],
    taxonomy: Taxonomy,
    model: str,
    prompt_version: str,
) -> dict:
    gold = {label.refnr: label_prediction(label, taxonomy) for label in labels if label.answer}
    joined = {refnr: f"{t.title}\n{t.description}" for refnr, t in texts.items()}

    systems = [("keywords", "Keyword search (baseline)", keyword_predictions(joined, taxonomy))]
    current = current_answers(results, model, prompt_version)
    systems += [
        (
            f"{model}/{prompt_version}",
            f"Claude ({model}, prompt {prompt_version})",
            answer_predictions(current, taxonomy, joined, counted_only=False),
        ),
        (
            f"{model}/{prompt_version}/counted",
            f"Claude as counted on the site ({model}, prompt {prompt_version})",
            answer_predictions(current, taxonomy, joined, counted_only=True),
        ),
    ]
    for old_model, old_prompt in _older_versions(results, model, prompt_version, set(gold)):
        answers = current_answers(results, old_model, old_prompt)
        systems.append(
            (
                f"{old_model}/{old_prompt}",
                f"Claude ({old_model}, prompt {old_prompt})",
                answer_predictions(answers, taxonomy, joined, counted_only=False),
            )
        )

    listed = {name.casefold() for name in taxonomy.names()}
    scored_systems = [score_system(id_, name, gold, preds, listed) for id_, name, preds in systems]
    main = dict((s[0], s[2]) for s in systems)[f"{model}/{prompt_version}/counted"]
    return {
        "labels": len(gold),
        "model": model,
        "prompt_version": prompt_version,
        "systems": scored_systems,
        "skills": per_skill(gold, main, listed),
    }


def label_prediction(label: Label, taxonomy: Taxonomy) -> Prediction:
    answer = label.answer
    if answer is None:
        raise ValueError(f"label {label.refnr} has no answer")
    return Prediction.of(
        ((skill_name(item.name, taxonomy), item.required) for item in answer.skills),
        fields={"role": answer.role, "seniority": answer.seniority, "remote": answer.remote},
        languages=_languages((item.language, item.level) for item in answer.languages),
    )


def keyword_predictions(texts: dict[str, str], taxonomy: Taxonomy) -> dict[str, Prediction]:
    return {
        refnr: Prediction.of((name, None) for name in taxonomy.find_in_text(text))
        for refnr, text in texts.items()
    }


def answer_predictions(
    answers: list[Record], taxonomy: Taxonomy, texts: dict[str, str], counted_only: bool
) -> dict[str, Prediction]:
    """Predictions from saved answers, with skills named the way silver names them."""
    rows: dict[str, list[tuple[str, bool | None]]] = defaultdict(list)
    for row in skill_rows(answers, taxonomy, texts):
        if counted_only and not (row["in_text"] or row["general"]):
            continue
        rows[row["refnr"]].append((row["skill"], row["required"]))
    return {
        a["refnr"]: Prediction.of(
            rows.get(a["refnr"], []),
            fields={f: a["output"][f] for f in FIELDS},
            languages=_languages((i["language"], i["level"]) for i in a["output"]["languages"]),
        )
        for a in answers
    }


def score_system(
    system_id: str,
    name: str,
    gold: dict[str, Prediction],
    predictions: dict[str, Prediction],
    listed: set[str],
) -> dict:
    refnrs = sorted(set(gold) & set(predictions))
    pairs = [(gold[r], predictions[r]) for r in refnrs]
    in_list = [compare_sets(set(g.skills) & listed, set(p.skills) & listed) for g, p in pairs]
    every = [compare_sets(set(g.skills), set(p.skills)) for g, p in pairs]
    result: dict = {"id": system_id, "name": name, "postings": len(refnrs)}
    result["skills"] = set_scores(in_list) if pairs else None
    result["all_skills"] = set_scores(every) if pairs else None

    has_fields = any(p.fields for _, p in pairs)
    result["required"] = required_scores(pairs) if has_fields else None
    for name_ in FIELDS:
        result[name_] = (
            accuracy_scores([(g.fields[name_], p.fields[name_]) for g, p in pairs])
            if has_fields
            else None
        )
    if has_fields:
        language_counts = [compare_sets(set(g.languages), set(p.languages)) for g, p in pairs]
        result["languages"] = set_scores(language_counts)
        result["language_level"] = accuracy_scores(
            [
                (g.languages[lang], p.languages[lang])
                for g, p in pairs
                for lang in set(g.languages) & set(p.languages)
            ]
        )
    else:
        result["languages"] = result["language_level"] = None
    return result


def required_scores(pairs: list[tuple[Prediction, Prediction]]) -> dict:
    """For skills both sides found: is required the same? Grouped by posting, so the
    interval treats a posting's skills as one draw."""
    per_posting = [
        [
            (g.skills[k], p.skills[k])
            for k in g.skills.keys() & p.skills.keys()
            if p.skills[k] is not None
        ]
        for g, p in pairs
    ]
    flat = [pair for posting in per_posting for pair in posting]

    def score(postings: Iterable[list[tuple[bool | None, bool | None]]]) -> float | None:
        return accuracy([g == p for posting in postings for g, p in posting])

    return {
        "n": len(flat),
        "accuracy": scored(score(per_posting), bootstrap(per_posting, score)),
        "required_as_nice": sum(1 for g, p in flat if g and not p),
        "nice_as_required": sum(1 for g, p in flat if not g and p),
    }


def per_skill(
    gold: dict[str, Prediction], predictions: dict[str, Prediction], listed: set[str]
) -> list[dict]:
    """Precision and recall per skill for one system, most labeled skills first."""
    tally: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    names: dict[str, str] = {}
    for refnr in set(gold) & set(predictions):
        g, p = gold[refnr], predictions[refnr]
        for key in g.skills.keys() | p.skills.keys():
            names.setdefault(key, g.names.get(key) or p.names[key])
            counts = tally[key]
            counts[0] += key in g.skills and key in p.skills
            counts[1] += key in p.skills and key not in g.skills
            counts[2] += key in g.skills and key not in p.skills
    rows = []
    for key, (tp, fp, fn) in tally.items():
        if tp + max(fp, fn) < MIN_SKILL_MENTIONS:
            continue
        counts = [SetCounts(tp, fp, fn)]
        rows.append(
            {
                "skill": names[key],
                "in_skill_list": key in listed,
                "labeled": tp + fn,
                "predicted": tp + fp,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": _round(precision(counts)),
                "recall": _round(recall(counts)),
            }
        )
    return sorted(rows, key=lambda r: (-r["labeled"], -r["predicted"], r["skill"]))


def skill_name(raw: str, taxonomy: Taxonomy) -> str:
    """The list name for a known skill, else the name with tidy spaces (like silver)."""
    tidy = " ".join(raw.split())
    return taxonomy.normalize(tidy) or tidy


def _languages(items: Iterable[tuple[str, str]]) -> dict[str, str]:
    found: dict[str, str] = {}
    for language, level in items:
        found.setdefault(language, level)  # the first level wins, like silver
    return found


def _older_versions(
    results: list[Record], model: str, prompt_version: str, refnrs: set[str]
) -> list[tuple[str, str]]:
    versions = {
        (r["model"], r["prompt_version"])
        for r in results
        if r["status"] == "ok" and r["refnr"] in refnrs
    }
    return sorted(versions - {(model, prompt_version)})


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)
