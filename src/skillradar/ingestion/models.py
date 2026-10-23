"""Shapes of the Jobsuche API responses."""

import re
from typing import Any

from pydantic import BaseModel, Field

# Postings are kept as raw dicts, so bronze stores exactly what the API sent.
Posting = dict[str, Any]

# Refnrs come from the API and end up in URLs and files, so only allow safe characters.
REFNR_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")


class SearchPage(BaseModel):
    postings: list[Posting] = Field(default_factory=list, alias="ergebnisliste")
    total: int = Field(default=0, alias="maxErgebnisse")


def is_valid_refnr(value: object) -> bool:
    return isinstance(value, str) and REFNR_PATTERN.fullmatch(value) is not None


def refnr_of(posting: Posting) -> str | None:
    """The posting's refnr, or None if it is missing or unsafe."""
    refnr = posting.get("referenznummer")
    return refnr if is_valid_refnr(refnr) else None
