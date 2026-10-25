"""The shape of the answer for one posting.

The pydantic models check answers. OUTPUT_SCHEMA is sent to the API, which makes Claude
return exactly this shape. Both are built from the same lists, so they cannot drift apart.
"""

from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

Role = Literal[
    "data_engineer",
    "data_scientist",
    "data_analyst",
    "ml_engineer",
    "backend_developer",
    "frontend_developer",
    "fullstack_developer",
    "mobile_developer",
    "devops_engineer",
    "embedded_engineer",
    "software_engineer",
    "it_security",
    "it_administration",
    "sap_erp",
    "it_project_manager",
    "other_tech",
    "not_tech",
]
Seniority = Literal["student", "junior", "mid", "senior", "lead", "unknown"]
Remote = Literal["onsite", "hybrid", "remote", "unknown"]
Level = Literal["basic", "good", "fluent", "native", "unknown"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SkillMention(Strict):
    name: str = Field(min_length=1, max_length=80)
    required: bool


class LanguageRequirement(Strict):
    language: str = Field(min_length=1, max_length=40)
    level: Level


class Extraction(Strict):
    role: Role
    seniority: Seniority
    remote: Remote
    languages: list[LanguageRequirement]
    skills: list[SkillMention]


def _enum(values: Any) -> dict[str, Any]:
    return {"type": "string", "enum": list(get_args(values))}


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


OUTPUT_SCHEMA = _object(
    {
        "role": _enum(Role),
        "seniority": _enum(Seniority),
        "remote": _enum(Remote),
        "languages": {
            "type": "array",
            "items": _object({"language": {"type": "string"}, "level": _enum(Level)}),
        },
        "skills": {
            "type": "array",
            "items": _object({"name": {"type": "string"}, "required": {"type": "boolean"}}),
        },
    }
)
