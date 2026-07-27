"""Auto-save, resume, and output storage."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from benchmark.models import RunResult

logger = logging.getLogger(__name__)


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_run_result(result: RunResult, output_dir: str | Path) -> Path:
    """Save a single run result to:
    output_dir/run_<timestamp>/<model>/<defender>.json
    """
    output_path = Path(output_dir)
    run_dir = _ensure_dir(output_path / f"run_{result.run_id}")
    model_dir = _ensure_dir(run_dir / result.model)
    file_path = model_dir / f"{result.defender}.json"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(result.to_template_dict(), indent=2, ensure_ascii=False))

    logger.info("Saved result: %s", file_path)
    return file_path


def save_model_summary(results: list[RunResult], output_dir: str | Path, model_name: str) -> Path:
    """Save a summary JSON for all defenders of one model."""
    output_path = Path(output_dir)
    run_id = results[0].run_id if results else datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = _ensure_dir(output_path / f"run_{run_id}")
    model_dir = _ensure_dir(run_dir / model_name)
    file_path = model_dir / "summary.json"

    data = {
        "run_id": run_id,
        "model": model_name,
        "scenario": results[0].scenario if results else "",
        "defenders": {
            r.defender: r.to_template_dict() for r in results
        },
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info("Saved summary: %s", file_path)
    return file_path


def load_partial_results(output_dir: str | Path, run_id: str, model_name: str) -> dict[str, RunResult]:
    """Load previously saved defender results for resumption.

    Returns dict of defender_name -> RunResult.
    """
    output_path = Path(output_dir)
    model_dir = output_path / f"run_{run_id}" / model_name

    if not model_dir.exists():
        return {}

    results: dict[str, RunResult] = {}
    for file_path in model_dir.glob("*.json"):
        if file_path.name == "summary.json":
            continue
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = RunResult.model_validate(data)
        results[result.defender] = result

    return results


def get_run_id() -> str:
    """Generate a run ID based on current timestamp."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")
