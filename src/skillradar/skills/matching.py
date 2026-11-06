"""Find a skill's name or spellings in a posting text.

Used to check if a posting names a skill (in_text) and to highlight it on the page, so
both always agree. Matching ignores case, and a space or hyphen in a term may be a
space, a hyphen or nothing in the text ("Data Warehouse" finds "Data-Warehouse").
"""

import re
from functools import lru_cache

# Postings use several dash characters; they count as a normal hyphen. One character
# becomes one character, so positions found in the prepared text fit the original.
DASHES = str.maketrans({c: "-" for c in "‐‑‒–—­"})


def prepare(text: str) -> str:
    return text.translate(DASHES)


@lru_cache(maxsize=4096)
def pattern(term: str) -> re.Pattern[str] | None:
    parts = [part for part in re.split(r"[\s-]+", prepare(term).strip()) if part]
    if not parts:
        return None
    body = r"[\s-]?".join(re.escape(part) for part in parts)
    # Not inside another word: "Java" is not found in "JavaScript", "C" not in "C++".
    return re.compile(rf"(?<![\w#+.]){body}(?![\w#+])", re.IGNORECASE)


def written_in(text: str, term: str) -> bool:
    """Is the term in a prepared text?"""
    found = pattern(term)
    return found is not None and found.search(text) is not None


def spans(text: str, term: str) -> list[tuple[int, int]]:
    """Start and end of every place the term is in a prepared text."""
    found = pattern(term)
    return [] if found is None else [m.span() for m in found.finditer(text)]
