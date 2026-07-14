"""Configuration loader — validates config.yaml via Pydantic."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """Configuration for an LLM provider."""
    provider: str
    model: str
    api_key: str = ""
    api_base: str = ""
    max_tokens: int | None = None       # None = use provider default
    temperature: float | None = None    # None = use provider default


class OutputConfig(BaseModel):
    """Output settings."""
    dir: str = "./results"
    format: str = "json"
    auto_save: bool = True


class Config(BaseModel):
    """Top-level configuration."""
    reviewer: LLMConfig
    models_to_test: list[LLMConfig]
    scenarios: list[str]
    defender_variants: list[str] = Field(default_factory=lambda: ["weak", "normal", "aggressive"])
    output: OutputConfig = Field(default_factory=OutputConfig)


def _substitute_env_vars(value: str) -> str:
    """Replace ${VAR_NAME} with environment variable values."""
    def _replace(match: re.Match) -> str:
        var = match.group(1)
        env_val = os.environ.get(var)
        return env_val if env_val is not None else match.group(0)
    return re.sub(r'\$\{(\w+)\}', _replace, value)


def _substitute_env_vars_recursive(obj):
    """Recursively substitute environment variables in strings."""
    if isinstance(obj, str):
        return _substitute_env_vars(obj)
    elif isinstance(obj, dict):
        return {k: _substitute_env_vars_recursive(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_substitute_env_vars_recursive(item) for item in obj]
    return obj


def load_config(path: str | Path) -> Config:
    """Load and validate a YAML config file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise ValueError(f"Empty config file: {path}")

    # Substitute environment variables
    raw = _substitute_env_vars_recursive(raw)

    return Config.model_validate(raw)
