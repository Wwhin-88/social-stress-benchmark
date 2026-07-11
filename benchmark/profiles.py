"""Profile presets for benchmark configuration.

Profiles override config.yaml settings to control benchmark scope.
- quick:     1 model, 1 scenario, 1 defender (weak)
- full:      everything from config
- regression: all models, 1 scenario, 1 defender (normal)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Profile:
    """A named profile that overrides config.yaml settings."""

    name: str
    description: str
    overrides: dict[str, Any] = field(default_factory=dict)


PROFILES: dict[str, Profile] = {
    "quick": Profile(
        name="quick",
        description="Быстрая проверка — 1 модель, 1 сценарий, 1 defender",
        overrides={
            "models": 1,
            "scenarios": 1,
            "defender_variants": ["weak"],
        },
    ),
    "full": Profile(
        name="full",
        description="Полный прогон — всё из конфига",
        overrides={},
    ),
    "regression": Profile(
        name="regression",
        description="Регрессия — все модели, 1 сценарий, 1 defender",
        overrides={
            "scenarios": 1,
            "defender_variants": ["normal"],
        },
    ),
}


def get_profile(name: str) -> Profile | None:
    """Get a profile by name (case-insensitive)."""
    return PROFILES.get(name.lower())


def list_profiles() -> list[Profile]:
    """Return all available profiles."""
    return list(PROFILES.values())


def profile_names() -> list[str]:
    """Return all available profile names."""
    return list(PROFILES.keys())
