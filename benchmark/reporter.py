"""Terminal output and JSON report generation."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from benchmark.models import RunResult, GateResult
from rich.console import Console
from rich.panel import Panel

logger = logging.getLogger(__name__)
console = Console()


def _gate_str(gate: GateResult) -> str:
    if gate.passed:
        return "[green]PASS ✓[/green]"
    return "[red]FAIL ✗[/red]"


def print_run_result(result: RunResult) -> None:
    """Print a single run result as a Rich panel."""
    gate_formatted = _gate_str(result.gate)
    failure_modes = result.failure_modes.detected
    failure_str = ", ".join(failure_modes) if failure_modes else "[dim]none[/dim]"

    content = (
        f"[bold]Model:[/bold] {result.model}\n"
        f"[bold]Scenario:[/bold] {result.scenario}\n"
        f"[bold]Defender:[/bold] {result.defender}\n"
        f"[bold]Gate:[/bold] {gate_formatted}\n"
        f"[bold]Composite Score:[/bold] {result.composite_score}\n"
        f"[bold]Failure Modes:[/bold] {failure_str}"
    )

    console.print()
    console.print(Panel(
        content,
        title="[bold]Run Result[/bold]",
        border_style="bright_blue",
        padding=(1, 2),
    ))


def print_header(title: str) -> None:
    """Print a clean section header using Rich Panel."""
    console.print()
    console.print(Panel(
        f"[bold]{title}[/bold]",
        border_style="bright_blue",
        padding=(0, 2),
    ))


def write_json_report(results: list[RunResult], output_path: str | Path) -> None:
    """Write a comprehensive JSON report for all runs."""
    report = {
        "benchmark": "Social Stress Benchmark",
        "version": "1.3.0",
        "runs": [r.to_template_dict() for r in results],
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.parent / f".{path.name}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)

    logger.info("Report written to %s", path)
    console.print(f"\n[bold]Report:[/bold] {path}")
