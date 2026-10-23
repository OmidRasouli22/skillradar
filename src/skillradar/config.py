"""Load settings from config/search.yaml."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, HttpUrl, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "search.yaml"
DATA_DIR = PROJECT_ROOT / "data"


class ApiConfig(BaseModel):
    base_url: HttpUrl
    api_key: str
    page_size: int = Field(gt=0, le=100)
    request_delay_seconds: float = Field(ge=0)
    timeout_seconds: float = Field(gt=0)
    max_retries: int = Field(ge=0)

    @field_validator("base_url")
    @classmethod
    def require_https(cls, url: HttpUrl) -> HttpUrl:
        if url.scheme != "https":
            raise ValueError("base_url must use https")
        return url


class SearchConfig(BaseModel):
    api: ApiConfig
    radius_km: int = Field(gt=0)
    cities: list[str] = Field(min_length=1)
    terms: list[str] = Field(min_length=1)

    def queries(self) -> list[tuple[str, str]]:
        """All (term, city) pairs to search."""
        return [(term, city) for city in self.cities for term in self.terms]

    def only(
        self, cities: list[str] | None = None, terms: list[str] | None = None
    ) -> "SearchConfig":
        """Copy limited to some of the configured cities and terms."""
        unknown_cities = set(cities or []) - set(self.cities)
        unknown_terms = set(terms or []) - set(self.terms)
        unknown = unknown_cities | unknown_terms
        if unknown:
            raise ValueError(f"not in config: {', '.join(sorted(unknown))}")
        return self.model_copy(
            update={"cities": cities or self.cities, "terms": terms or self.terms}
        )


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> SearchConfig:
    with path.open(encoding="utf-8") as f:
        return SearchConfig.model_validate(yaml.safe_load(f))
