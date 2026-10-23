"""Load settings from config/search.yaml."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, HttpUrl

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


class SearchConfig(BaseModel):
    api: ApiConfig
    radius_km: int = Field(gt=0)
    cities: list[str] = Field(min_length=1)
    terms: list[str] = Field(min_length=1)

    def queries(self) -> list[tuple[str, str]]:
        """All (term, city) pairs to search."""
        return [(term, city) for city in self.cities for term in self.terms]


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> SearchConfig:
    with path.open(encoding="utf-8") as f:
        return SearchConfig.model_validate(yaml.safe_load(f))
