"""Shapes of the Jobsuche API responses."""

from typing import Any

from pydantic import BaseModel, Field

# Postings are kept as raw dicts, so bronze stores exactly what the API sent.
Posting = dict[str, Any]


class SearchPage(BaseModel):
    postings: list[Posting] = Field(default_factory=list, alias="ergebnisliste")
    total: int = Field(default=0, alias="maxErgebnisse")
