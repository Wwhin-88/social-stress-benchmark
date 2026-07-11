"""Scenario loader for the Social Stress Benchmark."""

from pathlib import Path
import yaml

from benchmark.models import Scenario


def load_scenario(name: str) -> Scenario:
    """Load a scenario by name from the scenarios directory."""
    path = Path(__file__).parent / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Scenario '{name}' not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Scenario.model_validate(data)


def list_scenarios() -> list[str]:
    """List available scenario names."""
    scenarios_dir = Path(__file__).parent
    return [p.stem for p in scenarios_dir.glob("*.yaml")]
