"""Scores for one system against the labels.

Skills and languages are sets per posting, scored with micro precision and recall: all
(posting, skill) pairs together, so a posting with many skills counts more. Role,
seniority and remote are scored with accuracy. Each number has a 95% bootstrap interval:
the postings are drawn again with replacement many times, and the interval holds the
middle 95% of the results. The interval shows how much the number could move with
another sample of the same size.
"""

import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass

BOOTSTRAP_ROUNDS = 1000
SEED = 7


@dataclass(frozen=True)
class SetCounts:
    tp: int
    fp: int
    fn: int


def compare_sets(gold: set[str], predicted: set[str]) -> SetCounts:
    return SetCounts(tp=len(gold & predicted), fp=len(predicted - gold), fn=len(gold - predicted))


def precision(counts: Sequence[SetCounts]) -> float | None:
    tp = sum(c.tp for c in counts)
    found = tp + sum(c.fp for c in counts)
    return tp / found if found else None


def recall(counts: Sequence[SetCounts]) -> float | None:
    tp = sum(c.tp for c in counts)
    wanted = tp + sum(c.fn for c in counts)
    return tp / wanted if wanted else None


def f1(counts: Sequence[SetCounts]) -> float | None:
    p, r = precision(counts), recall(counts)
    if p is None or r is None or p + r == 0:
        return None
    return 2 * p * r / (p + r)


def accuracy(hits: Sequence[bool]) -> float | None:
    return sum(hits) / len(hits) if hits else None


def bootstrap[T](
    items: Sequence[T],
    score: Callable[[Sequence[T]], float | None],
    rounds: int = BOOTSTRAP_ROUNDS,
    seed: int = SEED,
) -> tuple[float, float] | None:
    """95% interval of score over items drawn again with replacement."""
    if not items:
        return None
    rng = random.Random(seed)  # noqa: S311 - seeded, so a report can be repeated
    results = []
    for _ in range(rounds):
        value = score(rng.choices(items, k=len(items)))
        if value is not None:
            results.append(value)
    if not results:
        return None
    results.sort()
    low = results[int(0.025 * (len(results) - 1))]
    high = results[int(0.975 * (len(results) - 1))]
    return low, high


def scored(value: float | None, interval: tuple[float, float] | None) -> dict:
    return {
        "value": _round(value),
        "low": _round(interval[0]) if interval else None,
        "high": _round(interval[1]) if interval else None,
    }


def set_scores(counts: Sequence[SetCounts]) -> dict:
    return {
        "tp": sum(c.tp for c in counts),
        "fp": sum(c.fp for c in counts),
        "fn": sum(c.fn for c in counts),
        "precision": scored(precision(counts), bootstrap(counts, precision)),
        "recall": scored(recall(counts), bootstrap(counts, recall)),
        "f1": scored(f1(counts), bootstrap(counts, f1)),
    }


def accuracy_scores(pairs: Sequence[tuple[str, str]], top: int = 5) -> dict:
    """Accuracy of (correct, predicted) pairs and the most common mistakes."""
    hits = [gold == predicted for gold, predicted in pairs]
    mistakes = Counter((g, p) for g, p in pairs if g != p).most_common(top)
    return {
        "n": len(pairs),
        "accuracy": scored(accuracy(hits), bootstrap(hits, accuracy)),
        "mistakes": [{"correct": g, "predicted": p, "count": n} for (g, p), n in mistakes],
    }


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)
