"""Auto-save, resume, and output storage."""

from __future__ import annotations

import json
import logging
import os
import tempfile
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
    output_path = Path(output_dir).resolve()
    run_dir = _ensure_dir(output_path / f"run_{result.run_id}")
    model_dir = _ensure_dir(run_dir / result.model)
    file_path = model_dir / f"{result.defender}.json"

    tmp_path = file_path.parent / f".{file_path.name}.tmp"
    try:
        serialized = json.dumps(result.to_template_dict(), indent=2, ensure_ascii=False)
    except Exception:
        # Fallback: use Pydantic's native JSON dump
        serialized = result.model_dump_json(indent=2, exclude_none=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(serialized)
    os.replace(tmp_path, file_path)

    logger.info("Saved result: %s", file_path)
    return file_path


def save_model_summary(results: list[RunResult], output_dir: str | Path, model_name: str) -> Path:
    """Save a summary JSON for all defenders of one model."""
    output_path = Path(output_dir).resolve()
    run_id = results[0].run_id if results else datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = _ensure_dir(output_path / f"run_{run_id}")
    model_dir = _ensure_dir(run_dir / model_name)
    file_path = model_dir / "summary.json"

    try:
        data = {
            "run_id": run_id,
            "model": model_name,
            "scenario": results[0].scenario if results else "",
            "defenders": {
                r.defender: r.to_template_dict() for r in results
            },
        }
    except Exception:
        # Fallback: use Pydantic's native serialization
        data = {
            "run_id": run_id,
            "model": model_name,
            "scenario": results[0].scenario if results else "",
            "defenders": {
                r.defender: json.loads(r.model_dump_json(exclude_none=True)) for r in results
            },
        }

    tmp_path = file_path.parent / f".{file_path.name}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, file_path)

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

        # Convert template format to Pydantic format
        if "scoring" in data:
            scoring = data.pop("scoring", {})
            data["composite_score"] = scoring.get("composite_score", 0.0)
            data["failure_modes"] = scoring.get("failure_modes", {"detected": [], "flags": []})

        # Remove template-only keys
        for key in ("benchmark", "version", "status"):
            data.pop(key, None)

        # Fix subtest dicts — remove "status" key
        for st_key in ("subtest_1", "subtest_2", "subtest_3"):
            if st_key in data and isinstance(data[st_key], dict):
                data[st_key].pop("status", None)
                # Fix reviewer_scores: "unscored/untested" strings → None
                rs = data[st_key].get("reviewer_scores")
                if isinstance(rs, dict):
                    for metric in rs:
                        if isinstance(rs[metric], dict):
                            score_val = rs[metric].get("score")
                            if score_val == "unscored/untested":
                                rs[metric]["score"] = None
                # Fix path_weights/weights_applied: "unscored/untested" strings → 0.0
                for weights_key in ("path_weights", "weights_applied"):
                    pw = data[st_key].get(weights_key)
                    if isinstance(pw, dict):
                        for k, v in pw.items():
                            if v == "unscored/untested":
                                pw[k] = 0.0

        result = RunResult.model_validate(data)
        results[result.defender] = result

    return results


def get_run_id() -> str:
    """Generate a run ID based on current timestamp."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")
