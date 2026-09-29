import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class LLMSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    timeout_seconds: float = Field(default=60, gt=0)
    max_retries: int = Field(default=2, ge=0)


class BriefSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: float = Field(default=180, gt=0)
    recursion_limit: int = Field(default=30, gt=0)
    model_call_limit: int | None = Field(default=None, gt=0)
    tool_call_limit: int | None = Field(default=None, gt=0)

class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm: LLMSettings
    investment_brief: BriefSettings = Field(
        default_factory=BriefSettings
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Default for our current Poetry src-layout project.
    project_root = Path(__file__).resolve().parents[2]

    # Deployment can supply a different config-file location.
    config_path = Path(
        os.getenv(
            "FINANCIAL_ASSISTANT_CONFIG",
            str(project_root / "config.yaml"),
        )
    )

    with config_path.open(encoding="utf-8") as file:
        raw_config = yaml.safe_load(file)

    return Settings.model_validate(raw_config)