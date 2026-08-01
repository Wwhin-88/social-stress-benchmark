"""SSB CLI — main entry point for the Social Stress Benchmark.

Usage:
    ssb                  → Interactive REPL
    ssb run              → Single benchmark pass
    ssb sweep            → Multi-model sweep
    ssb results          → View benchmark history
    ssb report           → Generate report
    ssb resume           → Resume interrupted run
    ssb config           → Configuration management
    ssb compare          → Compare two runs
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
from rich.console import Console

from benchmark.config import Config, LLMConfig, load_config
from benchmark.engine import BenchmarkEngine
from benchmark.reporter import write_json_report, print_header
from benchmark.repl import (
    _apply_overrides,
    _apply_profile_to_cfg,
    _config_wizard,
    _count_styles,
    _dry_run,
    _generate_report,
    _list_runs,
    _load_config_safe,
    _print_results_list,
    _print_results_show,
    _print_sweep_summary,
    _resume_run,
    _run_benchmark,
    _run_sweep_internal,
    _show_config,
    run_repl,
)
from benchmark.storage import get_run_id, save_model_summary

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

console = Console()
logger = logging.getLogger(__name__)


# ===================================================================
# Main group
# ===================================================================

@click.group(invoke_without_command=True)
@click.pass_context
def ssb(ctx: click.Context) -> None:
    """Social Stress Benchmark — evaluate LLM behavior under social pressure.

    Without arguments, launches the Textual TUI.
    Use 'ssb repl' for the old interactive REPL.
    Use 'ssb run', 'ssb sweep', etc. for direct execution.
    """
    if ctx.invoked_subcommand is None:
        from benchmark.tui.app import run_tui
        run_tui()


# ===================================================================
# ssb repl — legacy interactive REPL
# ===================================================================

@ssb.command(name="repl")
def repl_cmd() -> None:
    """Launch the legacy interactive REPL (readline-based)."""
    run_repl()


# ===================================================================
# ssb run
# ===================================================================

@ssb.command()
@click.option("--config", default="config.yaml", help="Path to config YAML")
@click.option("--profile", default=None, help="Profile: quick, full, regression")
@click.option("--model", default=None, help="Model override (e.g. phi-4)")
@click.option("--scenario", default=None, help="Scenario override")
@click.option("--defender", default=None, help="Defender variant override (weak/normal/aggressive)")
@click.option("--dry-run", is_flag=True, help="Validate config and API keys without running")
@click.option("--output", default=None, help="Output directory override")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose debug logging")
def run(
    config: str,
    profile: str | None,
    model: str | None,
    scenario: str | None,
    defender: str | None,
    dry_run: bool,
    output: str | None,
    verbose: bool,
) -> None:
    """Run a single benchmark pass."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    cfg = _load_config_safe(config)
    if cfg is None:
        sys.exit(1)

    # Apply profile
    cfg = _apply_profile_to_cfg(cfg, profile, model)

    # Apply overrides
    cfg = _apply_overrides(cfg, model, scenario, defender, output)

    if dry_run:
        ok = _dry_run(cfg)
        sys.exit(0 if ok else 1)

    results = _run_benchmark(cfg, verbose=verbose)
    if results is None:
        sys.exit(1)

    if results:
        _print_sweep_summary(results)
        output_path = Path(cfg.output.dir) / f"run_{results[0].run_id}" / "report.json"
        write_json_report(results, output_path)
        console.print(f"  [bold]Report:[/bold] {output_path}")
    else:
        console.print("\n[yellow]No results generated.[/yellow]")


# ===================================================================
# ssb sweep
# ===================================================================

@ssb.command()
@click.option("--config", default="config.yaml", help="Path to config YAML")
@click.option("--models", default=None, help="Comma-separated model names (e.g. phi-4,gpt-4o)")
@click.option("--defenders", default=None, help="Comma-separated defender variants (e.g. weak,normal,aggressive)")
@click.option("--output", default=None, help="Output directory override")
@click.option("--dry-run", is_flag=True, help="Validate without running")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose debug logging")
def sweep(
    config: str,
    models: str | None,
    defenders: str | None,
    output: str | None,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Sweep multiple models × defenders × scenarios."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    cfg = _load_config_safe(config)
    if cfg is None:
        sys.exit(1)

    # Model override via --models
    if models:
        model_names = [m.strip() for m in models.split(",")]
        cfg.models_to_test = [
            LLMConfig(provider="openai", model=name, api_key="")
            for name in model_names
        ]

    # Defender override
    if defenders:
        cfg.defender_variants = [d.strip() for d in defenders.split(",")]

    # Output override
    if output:
        cfg.output.dir = output

    if dry_run:
        ok = _dry_run(cfg)
        sys.exit(0 if ok else 1)

    results = _run_sweep_internal(cfg)
    if results is None:
        sys.exit(1)

    if results:
        _print_sweep_summary(results)
        output_path = Path(cfg.output.dir) / f"run_{results[0].run_id}" / "report.json"
        write_json_report(results, output_path)
        console.print(f"  [bold]Report:[/bold] {output_path}")
    else:
        console.print("\n[yellow]No results generated.[/yellow]")


# ===================================================================
# ssb results
# ===================================================================

@ssb.command()
@click.argument("action", default="list")
@click.argument("run_id", default=None, required=False)
def results(action: str, run_id: str | None) -> None:
    """List or show benchmark results."""
    if action == "list":
        _print_results_list()
    elif action == "show":
        if not run_id:
            console.print("[yellow]Usage: ssb results show <run_id>[/yellow]")
            sys.exit(1)
        _print_results_show(run_id)
    else:
        console.print(f"[yellow]Unknown action: {action}. Use 'list' or 'show <run_id>'.[/yellow]")
        sys.exit(1)


# ===================================================================
# ssb report
# ===================================================================

@ssb.command()
@click.argument("run_id")
@click.option("--format", "fmt", default="json", help="Output format (json)")
def report(run_id: str, fmt: str) -> None:
    """Generate a report for a benchmark run."""
    _generate_report(run_id, fmt)


# ===================================================================
# ssb resume
# ===================================================================

@ssb.command()
@click.argument("run_id", default=None, required=False)
@click.option("--config", default="config.yaml", help="Path to config YAML")
def resume(run_id: str | None, config: str) -> None:
    """Resume an interrupted benchmark run."""
    _resume_run(run_id, config)


# ===================================================================
# ssb config
# ===================================================================

@ssb.command(name="config")
@click.argument("action", default="list")
@click.argument("key", default=None, required=False)
@click.argument("value", default=None, required=False)
@click.option("--config", "config_path", default="config.yaml", help="Path to config YAML")
def config_cmd(action: str, key: str | None, value: str | None, config_path: str) -> None:
    """Manage configuration: list, set, or init."""
    if action == "list":
        _show_config(config_path)
    elif action == "init":
        _config_wizard(config_path)
    elif action == "set":
        if not key or value is None:
            console.print("[yellow]Usage: ssb config set <key> <value>[/yellow]")
            sys.exit(1)
        from benchmark.repl import _config_set
        _config_set(key, value, config_path)
    else:
        console.print(f"[yellow]Unknown action: {action}. Use 'list', 'set', or 'init'.[/yellow]")
        sys.exit(1)


# ===================================================================
# ssb compare
# ===================================================================

@ssb.command()
@click.argument("run_a")
@click.argument("run_b")
def compare(run_a: str, run_b: str) -> None:
    """Compare two benchmark runs (extended)."""
    from benchmark.repl import _compare_runs
    _compare_runs(run_a, run_b)


# ===================================================================
# Entry point
# ===================================================================

if __name__ == "__main__":
    ssb()
