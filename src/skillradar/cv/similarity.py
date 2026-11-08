"""How alike two skills are, learned from the open postings.

Each skill is described by the skills it appears with (positive pointwise mutual
information, PPMI). Two skills are alike when they appear with the same other skills,
e.g. AWS and GCP both appear with Kubernetes, Terraform and CI/CD. This finds skills of
the same kind of job, not skills that replace each other: Python and Spark are alike
too. So it is used for two things only:

- how much a substitute from config/skill_families.yaml counts (AWS for Azure), and
- which known skills a missing skill builds on, for the learning plan.
"""

import math
from collections import Counter
from collections.abc import Iterable

from skillradar.skills.taxonomy import key

# Rarer skills have too few postings for a stable profile.
MIN_POSTINGS = 15


class Similarity:
    def __init__(self, postings: Iterable[Iterable[str]], min_postings: int = MIN_POSTINGS):
        """postings: the skill names of each posting."""
        sets = [{key(name) for name in skills} for skills in postings]
        sets = [s for s in sets if s]
        total = len(sets)
        counts = Counter(k for s in sets for k in s)
        self.common = {k for k, n in counts.items() if n >= min_postings}
        pairs: Counter[tuple[str, str]] = Counter()
        for s in sets:
            kept = sorted(s & self.common)
            for i, a in enumerate(kept):
                for b in kept[i + 1 :]:
                    pairs[(a, b)] += 1
        self._vectors: dict[str, dict[str, float]] = {k: {} for k in self.common}
        for (a, b), together in pairs.items():
            value = math.log(together * total / (counts[a] * counts[b]))
            if value > 0:
                self._vectors[a][b] = value
                self._vectors[b][a] = value
        self._norms = {
            k: math.sqrt(sum(v * v for v in vector.values())) for k, vector in self._vectors.items()
        }

    def of(self, a: str, b: str) -> float | None:
        """Cosine of the two profiles, 0 to 1; None when a skill is too rare to say."""
        ka, kb = key(a), key(b)
        if ka not in self.common or kb not in self.common:
            return None
        if ka == kb:
            return 1.0
        va, vb = self._vectors[ka], self._vectors[kb]
        norm = self._norms[ka] * self._norms[kb]
        if norm == 0:
            return 0.0
        shared = (set(va) & set(vb)) - {ka, kb}
        return sum(va[k] * vb[k] for k in shared) / norm
