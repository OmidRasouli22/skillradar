"""Load config/llm.yaml."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from skillradar.config import PROJECT_ROOT

DEFAULT_LLM_PATH = PROJECT_ROOT / "config" / "llm.yaml"


class Price(BaseModel):
    input: float = Field(ge=0)
    output: float = Field(ge=0)


class LlmSettings(BaseModel):
    model: str = Field(pattern=r"^[a-z0-9.-]{3,64}$")
    effort: Literal["low", "medium", "high"]
    max_tokens: int = Field(ge=1000, le=64000)
    batch_limit: int = Field(ge=1, le=100_000)
    prices: dict[str, Price]

    @model_validator(mode="after")
    def model_has_price(self) -> "LlmSettings":
        if self.model not in self.prices:
            raise ValueError(f"no price for model {self.model}")
        return self

    def batch_cost(self, input_tokens: int, output_tokens: int, model: str | None = None) -> float:
        """USD for a batch with these token counts. Batch requests cost half."""
        price = self.prices[model or self.model]
        return (input_tokens * price.input + output_tokens * price.output) / 1_000_000 / 2


def load_settings(path: Path = DEFAULT_LLM_PATH) -> LlmSettings:
    with path.open(encoding="utf-8") as f:
        return LlmSettings.model_validate(yaml.safe_load(f))
