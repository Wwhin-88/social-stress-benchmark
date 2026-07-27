"""Comprehensive test-run logger — captures every event during benchmark execution.

Writes JSON-lines to ``results/run_<id>/test_run.log`` — one JSON object per line.
Structured for grep-ability and post-hoc analysis.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────

class TestLogger:
    """Structured event logger for a single benchmark run.

    Usage::

        tlog = TestLogger(run_id, output_dir)
        tlog.start()
        tlog.log_llm_call(turn=1, provider="openai", model="gpt-4o",
                          prompt_preview="...", response_preview="...",
                          latency_ms=1234, status="success")
        tlog.log_reviewer_eval(turn=1, raw_scores={...}, parse_success=True)
        tlog.log_choice(subtest="subtest_2", dp="dp1",
                        options=["A: ...", "B: ...", "C: ..."],
                        chosen="A", weights={"AS": 2, "PS": 2})
        tlog.log_scoring(gate_passed=True, composite=12.0,
                         failure_modes=[], dv_weight=0.0)
        tlog.log_error(context="subtest_1/turn_2",
                       error_type="LLMError",
                       message="Timeout after 3 retries")
        tlog.finish(status="completed")

    Output format (one JSON object per line)::

        {"ts":"2026-07-27T12:00:00.123Z","event":"llm_call","turn":1,...}
        {"ts":"2026-07-27T12:00:05.456Z","event":"reviewer_eval","turn":1,...}
        ...
    """

    def __init__(self, run_id: str, output_dir: str | Path) -> None:
        self.run_id = run_id
        self.output_dir = Path(output_dir)
        self._file: Any = None
        self._started = False

    # ── lifecycle ──────────────────────────────────────────────────

    def _ensure_dir(self) -> Path:
        run_dir = self.output_dir / f"run_{self.run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def start(self) -> Path:
        """Open the log file and write the start-of-run record."""
        run_dir = self._ensure_dir()
        path = run_dir / "test_run.log"
        self._file = open(path, "w", encoding="utf-8")
        self._started = True
        self._write_event("run_start", {
            "run_id": self.run_id,
            "started_at": _ts(),
        })
        return path

    def finish(self, status: str = "completed") -> None:
        """Write end-of-run record and close the file."""
        if not self._started:
            return
        self._write_event("run_end", {
            "status": status,
            "finished_at": _ts(),
        })
        if self._file:
            self._file.close()
            self._file = None
        self._started = False

    # ── event loggers ───────────────────────────────────────────────

    def log_llm_call(
        self,
        *,
        turn: int | None = None,
        subtest: str = "subtest_1",
        provider: str,
        model: str,
        prompt_preview: str,
        response_preview: str,
        latency_ms: float,
        status: str = "success",
        error: str = "",
    ) -> None:
        self._write_event("llm_call", {
            "subtest": subtest,
            "turn": turn,
            "provider": provider,
            "model": model,
            "prompt_preview": prompt_preview[:500],
            "response_preview": response_preview[:500],
            "latency_ms": round(latency_ms, 2),
            "status": status,
            "error": error,
        })

    def log_reviewer_eval(
        self,
        *,
        turn: int,
        raw_scores: dict[str, Any],
        parse_success: bool,
        reviewer_provider: str = "",
        reviewer_model: str = "",
        latency_ms: float = 0.0,
    ) -> None:
        safe_scores = {k: (v if isinstance(v, (int, float, str, type(None), bool)) else str(v))
                       for k, v in raw_scores.items()}
        self._write_event("reviewer_eval", {
            "turn": turn,
            "reviewer": f"{reviewer_provider}/{reviewer_model}" if reviewer_provider else "",
            "latency_ms": round(latency_ms, 2),
            "parse_success": parse_success,
            "raw_scores": safe_scores,
        })

    def log_choice(
        self,
        *,
        subtest: str,
        dp: str | None = None,
        options: list[str],
        chosen: str,
        weights: dict[str, float],
    ) -> None:
        self._write_event("choice", {
            "subtest": subtest,
            "dp": dp,
            "options": options,
            "chosen": chosen,
            "weights_applied": weights,
        })

    def log_scoring(
        self,
        *,
        gate_passed: bool,
        composite_score: float,
        failure_modes: list[str],
        dv_weight: float,
    ) -> None:
        self._write_event("scoring", {
            "gate_passed": gate_passed,
            "gate_metric": "DV",
            "dv_weight": dv_weight,
            "composite_score": composite_score,
            "failure_modes": failure_modes,
        })

    def log_error(
        self,
        *,
        context: str,
        error_type: str,
        message: str,
        traceback: str = "",
    ) -> None:
        self._write_event("error", {
            "context": context,
            "error_type": error_type,
            "message": message[:1000],
            "traceback": traceback[:2000] if traceback else "",
        })

    def log_config(
        self,
        *,
        reviewer: str,
        test_model: str,
        scenario: str,
        defender: str,
        profile: str = "",
    ) -> None:
        self._write_event("config", {
            "reviewer": reviewer,
            "test_model": test_model,
            "scenario": scenario,
            "defender": defender,
            "profile": profile,
        })

    # ── internal ────────────────────────────────────────────────────

    def _write_event(self, event: str, data: dict[str, Any]) -> None:
        if not self._started or not self._file:
            return
        record = {"ts": _ts(), "event": event, **data}
        try:
            self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._file.flush()
        except Exception:
            pass  # Never let logging failures crash the benchmark


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _ts() -> str:
    """ISO 8601 timestamp with millisecond precision and Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
           f"{int(time.time() * 1000) % 1000:03d}Z"
