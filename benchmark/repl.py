"""Interactive REPL for the Social Stress Benchmark.

Usage:  ssb> /run --profile quick --model phi-4
        ssb> /sweep --models phi-4,gpt-4o
        ssb> /help
        ssb> /exit

Features:
- Tab completion for slash-commands
- Rich tables, panels, and prompts
- Pulsing progress bar for sweep/run with multiple combinations
- Config wizard (/config init)
- Partial resume (/resume)
- Dry-run support
"""

from __future__ import annotations

import copy
import json
import logging
import os
import readline
import shlex
import sys
import threading
import time
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from benchmark import __version__ as benchmark_version
from benchmark.config import Config, LLMConfig, load_config
from benchmark.models import RunResult
from benchmark.profiles import get_profile, list_profiles, profile_names
from benchmark.reporter import print_header, write_json_report
from benchmark.runner import run_scenario
from benchmark.storage import get_run_id, load_partial_results, save_model_summary

logger = logging.getLogger(__name__)
console = Console()

# ===================================================================
# Readline tab completion
# ===================================================================

REPL_COMMANDS = [
    "/run",
    "/sweep",
    "/resume",
    "/results",
    "/report",
    "/models",
    "/scenarios",
    "/config",
    "/export",
    "/help",
    "/clear",
    "/exit",
]

SUB_COMMANDS: dict[str, list[str]] = {
    "/results": ["list", "show", "compare", "delete"],
    "/config": ["list", "set", "init", "get", "add", "remove", "save"],
    "/models": ["list", "add", "remove", "test"],
    "/scenarios": ["list", "show"],
    "/report": [],
    "/run": [],
    "/sweep": [],
    "/resume": [],
    "/export": [],
}

REPL_BANNER = Panel(
    "[bold bright_blue]Social Stress Benchmark[/bold bright_blue]\n"
    f"[dim]v{benchmark_version} REPL[/dim]  \u00b7  "
    "[green]/help[/green] for commands  \u00b7  "
    "[green]/exit[/green] to quit",
    border_style="bright_blue",
    padding=(1, 2),
    subtitle="[dim]interactive shell[/dim]",
)


# ===================================================================
# Input helpers (fix Delete key in Rich Prompt.ask)
# ===================================================================
# Rich Prompt.ask has a known readline compatibility issue where
# Delete/Backspace keys misbehave. These helpers render the prompt
# via Rich (supporting markup) but use plain input() for the actual
# readline call, restoring proper key handling.

def _ask_text(prompt: str, default: str = "") -> str:
    """Ask for text input with readline-safe prompt rendering."""
    sys.stdout.write("  ")
    console.print(prompt, end="")
    try:
        value = input()
    except EOFError:
        console.print()
        return default or ""
    except KeyboardInterrupt:
        console.print()
        raise
    if not value:
        return default or ""
    return value.strip()


def _ask_choice(prompt: str, choices: list[str], default: str | None = None) -> str:
    """Ask user to pick from a list of choices."""
    sys.stdout.write("  ")
    console.print(prompt, end="")
    if default:
        console.print(f" [{default}]", style="dim", end="")
    console.print(" ", end="")
    try:
        value = input().strip().lower()
    except EOFError:
        console.print()
        return default or choices[0]
    except KeyboardInterrupt:
        console.print()
        raise
    if not value and default:
        return default
    while value not in [c.lower() for c in choices]:
        console.print(f"  [yellow]Choose from: {', '.join(choices)}[/yellow]")
        sys.stdout.write("  ")
        console.print(prompt, end=" ")
        try:
            value = input().strip().lower()
        except EOFError:
            console.print()
            return default or choices[0]
        except KeyboardInterrupt:
            console.print()
            raise
    # Return original case version
    for c in choices:
        if c.lower() == value:
            return c
    return value


def _ask_confirm(prompt: str, default: bool = True) -> bool:
    """Ask a yes/no question."""
    hint = " [Y/n]" if default else " [y/N]"
    sys.stdout.write("  ")
    console.print(prompt + hint, end=" ")
    try:
        value = input().strip().lower()
    except EOFError:
        console.print()
        return default
    except KeyboardInterrupt:
        console.print()
        raise
    if not value:
        return default
    return value.startswith("y")


def _arrow_select(prompt: str, choices: list[str]) -> str:
    """Interactive arrow-key selection with Rich rendering."""
    import termios
    import tty

    def _getch() -> str:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if not ch:  # EOF
                raise EOFError("Terminal closed")
            if ch == "\x03":  # Ctrl+C
                raise KeyboardInterrupt()
            if ch == "\x1b":
                ch += sys.stdin.read(2)
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    selected = 0
    console.print(f"  {prompt}")

    while True:
        for i, choice in enumerate(choices):
            if i == selected:
                console.print(f"    [bright_cyan]> {choice}[/bright_cyan]")
            else:
                console.print(f"      {choice}")

        ch = _getch()

        # Clear the rendered lines
        for _ in range(len(choices)):
            sys.stdout.write("\033[F\033[K")
        sys.stdout.flush()

        if ch == "\x1b[A":  # Up arrow
            selected = (selected - 1) % len(choices)
        elif ch == "\x1b[B":  # Down arrow
            selected = (selected + 1) % len(choices)
        elif ch in ("\r", "\n"):  # Enter
            console.print()
            return choices[selected]


def _multi_arrow_select(
    prompt: str,
    choices: list[str],
    defaults: list[bool] | None = None,
    hint: str = "\u2191/\u2193 move \u00b7 Enter toggle \u00b7 Shift+Enter confirm",
) -> list[str]:
    """Interactive multi-select with arrow keys, Enter to toggle, Shift+Enter to confirm.
    
    Returns list of selected choices.
    """
    import termios
    import tty
    import select

    def _getch(timeout: float = 0.05) -> str:
        """Read one keypress. For escape sequences, reads continuation bytes
        with a short timeout so plain Escape returns immediately while
        arrow keys / CSI sequences are captured fully."""
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if not ch:  # EOF
                raise EOFError("Terminal closed")
            if ch == "\x03":  # Ctrl+C
                raise KeyboardInterrupt()
            if ch == "\x1b":
                # Read continuation bytes with timeout
                rest = ""
                while select.select([sys.stdin], [], [], timeout)[0]:
                    b = sys.stdin.read(1)
                    rest += b
                    # Stop at a letter or tilde (end of CSI sequence)
                    if b.isalpha() or b == "~":
                        break
                return ch + rest
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    selected_idx = 0
    checked = [False] * len(choices)
    if defaults:
        for i, d in enumerate(defaults):
            if i < len(checked) and d:
                checked[i] = True

    while True:
        # Render
        console.print(f"  {prompt}")
        for i, choice in enumerate(choices):
            check = "[bright_green]\u2713[/bright_green]" if checked[i] else " "
            if i == selected_idx:
                console.print(f"    [bright_cyan][{check}] {choice}[/bright_cyan]")
            else:
                console.print(f"      [{check}] {choice}")

        console.print(f"  [dim]{hint}[/dim]")

        ch = _getch()

        # Determine action
        if ch == "\x1b[A":  # Up arrow
            selected_idx = (selected_idx - 1) % len(choices)
        elif ch == "\x1b[B":  # Down arrow
            selected_idx = (selected_idx + 1) % len(choices)
        elif ch == "\x1b":  # Plain Escape \u2192 confirm as fallback
            n_lines = len(choices) + 2
            for _ in range(n_lines):
                sys.stdout.write("\033[F\033[K")
            sys.stdout.flush()
            console.print(f"  [dim]Selected: {sum(checked)}/{len(choices)}[/dim]")
            return [choices[i] for i in range(len(choices)) if checked[i]]
        elif ch in ("\r", "\n"):  # Enter \u2192 toggle current item
            checked[selected_idx] = not checked[selected_idx]
        elif ch.startswith("\x1b["):  # CSI sequence (Shift+Enter or other)
            # Normalize: strip leading \x1b[ to compare the rest
            csi = ch[2:]  # after \x1b[
            # Shift+Enter: \x1b[13;2u (kitty) or \x1b[27;2;13~ (xterm)
            if csi in ("13;2u", "27;2;13~"):
                n_lines = len(choices) + 2
                for _ in range(n_lines):
                    sys.stdout.write("\033[F\033[K")
                sys.stdout.flush()
                console.print(f"  [dim]Selected: {sum(checked)}/{len(choices)}[/dim]")
                return [choices[i] for i in range(len(choices)) if checked[i]]

        # Clear rendered lines (prompt + choices + hint = len(choices)+2 lines)
        n_lines = len(choices) + 2
        for _ in range(n_lines):
            sys.stdout.write("\033[F\033[K")
        sys.stdout.flush()


class REPLCompleter:
    """Readline tab completer for REPL commands."""

    def __init__(self) -> None:
        self.matches: list[str] = []

    def complete(self, text: str, state: int) -> str | None:
        if state == 0:
            self.matches = [c for c in REPL_COMMANDS if c.startswith(text)]
        try:
            return self.matches[state]
        except IndexError:
            return None


def _setup_readline() -> None:
    """Configure readline with tab completion (best-effort)."""
    try:
        completer = REPLCompleter()
        readline.set_completer(completer.complete)  # type: ignore[arg-type]
        readline.parse_and_bind("tab: complete")
        readline.set_history_length(200)
    except Exception:
        pass  # Tab completion is optional


# ===================================================================
# Pulsing progress bar
# ===================================================================

class PulsingBar:
    """Pulsing ASCII progress bar for sweep/run operations.

    Animates a bar that cyclically fills to current_progress %
    and drains back to 0%, signalling the process is alive.
    """

    BAR_WIDTH = 20

    def __init__(self, total: int, description: str = "Running") -> None:
        self.total = total
        self.completed = 0
        self.description = description
        self.running = False
        self._thread: threading.Thread | None = None

    @property
    def pct(self) -> float:
        return round(self.completed / max(self.total, 1) * 100, 2)

    def __enter__(self) -> PulsingBar:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()

    def start(self) -> None:
        """Start the pulsing animation in a daemon thread."""
        self.running = True
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the animation and clean up."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        # Clear the bar line
        sys.stdout.write("\r" + " " * (self.BAR_WIDTH + 20) + "\r")
        sys.stdout.flush()

    def _animate(self) -> None:
        """Background loop: pulse up to current_pct then down to 0."""
        while self.running:
            current_pct = int(self.pct)
            if current_pct == 0:
                self._draw(0)
                time.sleep(0.05)
                continue
            # Pulse up
            for i in range(current_pct + 1):
                if not self.running:
                    return
                self._draw(i)
                time.sleep(0.002)
            # Pulse down
            for i in range(current_pct, -1, -1):
                if not self.running:
                    return
                self._draw(i)
                time.sleep(0.002)

    def _draw(self, pct: int) -> None:
        """Render the bar line with carriage return."""
        filled = int(pct / 100 * self.BAR_WIDTH)
        filled_bar = "\033[96m" + "\u2588" * filled + "\033[0m"
        empty_bar = "\033[90m" + "\u2591" * (self.BAR_WIDTH - filled) + "\033[0m"
        # Percentages use comma as decimal separator per spec
        pct_str = f"{pct:.2f}".replace(".", ",")
        color = "\033[92m" if pct >= 100 else "\033[96m"
        sys.stdout.write(f"\r{self.description} {filled_bar}{empty_bar} {color}{pct_str}%\033[0m")
        sys.stdout.flush()


# ===================================================================
# Config helpers
# ===================================================================

def _apply_profile_to_cfg(
    cfg: Config,
    profile_name: str | None,
    model_override: str | None = None,
) -> Config:
    """Apply a profile and optional model override to a Config object."""
    cfg = copy.deepcopy(cfg)

    profile = get_profile(profile_name) if profile_name else get_profile("full")
    if profile is None:
        return cfg

    for key, value in profile.overrides.items():
        if key == "models":
            if model_override:
                matching = [m for m in cfg.models_to_test if m.model == model_override]
                if matching:
                    cfg.models_to_test = matching[:1]
                else:
                    cfg.models_to_test = [
                        LLMConfig(provider="openai", model=model_override, api_key="")
                    ]
            else:
                cfg.models_to_test = cfg.models_to_test[:1]
        elif key == "scenarios":
            cfg.scenarios = cfg.scenarios[:value]
        elif key == "defender_variants":
            cfg.defender_variants = list(value)

    # If model override given outside quick profile, still filter
    if model_override and profile_name not in (None, "quick"):
        matching = [m for m in cfg.models_to_test if m.model == model_override]
        if matching:
            cfg.models_to_test = matching[:1]

    return cfg


def _apply_overrides(
    cfg: Config,
    model_override: str | None = None,
    scenario_override: str | None = None,
    defender_override: str | None = None,
    output_override: str | None = None,
) -> Config:
    """Apply individual CLI overrides to a Config object."""
    cfg = copy.deepcopy(cfg)

    if model_override:
        matching = [m for m in cfg.models_to_test if m.model == model_override]
        if matching:
            cfg.models_to_test = matching[:1]
        else:
            cfg.models_to_test = [
                LLMConfig(provider="openai", model=model_override, api_key="")
            ]

    if scenario_override:
        cfg.scenarios = [scenario_override]

    if defender_override:
        cfg.defender_variants = [defender_override]

    if output_override:
        cfg.output.dir = output_override

    return cfg


def _load_config_safe(config_path: str) -> Config | None:
    """Load config, returning None on failure with user-facing message."""
    path = Path(config_path)
    if not path.exists():
        console.print(f"[red]❌ Config not found: {path}[/red]")
        console.print(f"[dim]   Copy [bold]config.example.yaml[/bold] → [bold]config.yaml[/bold] and edit it, or run [bold]ssb config init[/bold][/dim]")
        return None
    try:
        return load_config(path)
    except Exception as e:
        console.print(f"[red]❌ Failed to load config: {e}[/red]")
        return None


def _count_styles(cfg: Config) -> int:
    """Total combinations = models × scenarios × defenders."""
    return len(cfg.models_to_test) * len(cfg.scenarios) * len(cfg.defender_variants)


# ===================================================================
# Dry-run: validate config + API connectivity
# ===================================================================

def _dry_run(cfg: Config, config_path: str = "config.yaml") -> bool:
    """Validate config and check API keys / model availability.

    Returns True if all checks pass, False otherwise.
    """
    ok = True
    lines: list[str] = []

    # Reviewer section
    lines.append(f"[bold]Reviewer:[/bold] {cfg.reviewer.provider}/{cfg.reviewer.model}")
    if not cfg.reviewer.api_key:
        lines.append("  [yellow]No API key set for reviewer[/yellow]")
    else:
        key_preview = cfg.reviewer.api_key[:8] + "..." if len(cfg.reviewer.api_key) > 8 else "(set)"
        lines.append(f"  API key: {key_preview}")

    # Models section
    lines.append("")
    lines.append(f"[bold]Models to test:[/bold] {len(cfg.models_to_test)}")
    for m in cfg.models_to_test:
        key_status = "[green]key set[/green]" if m.api_key else "[yellow]no key[/yellow]"
        lines.append(f"  [bright_cyan]{m.provider}[/bright_cyan]/[green]{m.model}[/green] [{key_status}]")

    # Scenarios section
    lines.append("")
    lines.append(f"[bold]Scenarios:[/bold] {len(cfg.scenarios)}")
    for s in cfg.scenarios:
        scenario_path = Path("scenarios") / f"{s}.yaml"
        if scenario_path.exists():
            exists_str = "[green]found[/green]"
        else:
            exists_str = "[red]not found[/red]"
            ok = False
            # Debug: show what config actually contains (Bug 2 fix)
            try:
                import yaml as _yaml
                _raw = _yaml.safe_load(open(config_path, encoding="utf-8"))
                lines.append(f"    Config scenarios: {_raw.get('scenarios', 'MISSING')}")
                lines.append(f"    Checked path: {scenario_path.resolve()}")
            except Exception as _e:
                lines.append(f"    Config read error: {_e}")
        lines.append(f"  {s} [{exists_str}]")

    # Summary section
    lines.append("")
    lines.append(f"[bold]Defender variants:[/bold] {', '.join(cfg.defender_variants)}")
    lines.append(f"[bold]Total combinations:[/bold] {_count_styles(cfg)}")
    lines.append(f"[bold]Output directory:[/bold] {cfg.output.dir}")
    lines.append(f"[bold]Auto-save:[/bold] {'[green]yes[/green]' if cfg.output.auto_save else '[red]no[/red]'}")

    if ok:
        lines.append("")
        lines.append("[green]All checks passed.[/green]")
    else:
        lines.append("")
        lines.append("[yellow]Some checks need attention before running.[/yellow]")

    console.print(Panel(
        "\n".join(lines),
        title="[bold]Dry-Run Validation[/bold]",
        border_style="bright_blue",
        padding=(1, 2),
    ))
    return ok


# ===================================================================
# Engine run helpers
# ===================================================================

def _run_benchmark(cfg: Config, verbose: bool = False) -> list[RunResult] | None:
    """Run the benchmark engine, using pulsing bar for multi-combination runs.

    Returns list of RunResult on success, None on fatal error.
    """
    total = _count_styles(cfg)

    if total <= 1 and not verbose:
        # Single combination: run engine directly (it has its own output)
        from benchmark.engine import BenchmarkEngine

        engine = BenchmarkEngine(cfg)
        try:
            return engine.run()
        except KeyboardInterrupt:
            console.print("\n\n[yellow]⚠  Interrupted.[/yellow]")
            return None
        except Exception as e:
            console.print(f"\n[red]❌ Benchmark failed: {e}[/red]")
            logger.exception("Benchmark failed")
            return None
    else:
        # Multi-combination: manual iteration with pulsing bar
        return _run_sweep_internal(cfg)


def _run_sweep_internal(cfg: Config) -> list[RunResult] | None:
    """Iterate models × scenarios × defenders with pulsing progress bar."""
    results: list[RunResult] = []
    run_id = get_run_id()

    console.print(Panel(
        f"[bold]Sweep run:[/bold] [bright_cyan]{run_id}[/bright_cyan]\n"
        f"  Models: {len(cfg.models_to_test)}  \u00b7  "
        f"Scenarios: {len(cfg.scenarios)}  \u00b7  "
        f"Defenders: {len(cfg.defender_variants)}\n"
        f"  Total: [bold]{_count_styles(cfg)}[/bold] combinations",
        border_style="bright_blue",
        padding=(1, 2),
    ))

    total = _count_styles(cfg)
    completed = 0

    try:
        with PulsingBar(total, f"Sweeping {total} combinations") as bar:
            for model_cfg in cfg.models_to_test:
                for scenario_name in cfg.scenarios:
                    from scenarios import load_scenario

                    try:
                        scenario = load_scenario(scenario_name)
                    except Exception as e:
                        logger.error("Failed to load scenario '%s': %s", scenario_name, e)
                        completed += len(cfg.defender_variants)
                        bar.completed = completed
                        continue

                    for defender in cfg.defender_variants:
                        try:
                            result = run_scenario(
                                model_config=model_cfg,
                                reviewer_config=cfg.reviewer,
                                scenario=scenario,
                                defender_variant=defender,
                                output_dir=cfg.output.dir,
                                run_id=run_id,
                            )
                            results.append(result)
                        except KeyboardInterrupt:
                            raise
                        except Exception as e:
                            logger.error(
                                "Failed %s/%s/%s: %s",
                                model_cfg.model, scenario_name, defender, e,
                            )

                        completed += 1
                        bar.completed = completed

            # Save model summaries (only reached on successful completion)
            if results and cfg.output.auto_save:
                for model_cfg in cfg.models_to_test:
                    model_results = [r for r in results if r.model == model_cfg.model]
                    if model_results:
                        save_model_summary(model_results, cfg.output.dir, model_cfg.model)

        return results

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠  Interrupted.[/yellow]")
        return None


def _print_sweep_summary(results: list[RunResult]) -> None:
    """Print a summary table after sweep completes."""
    if not results:
        console.print("[yellow]No results generated.[/yellow]")
        return

    table = Table(
        title="Sweep Results",
        title_justify="left",
        header_style="bold cyan",
        row_styles=["", "dim"],
        box=box.ROUNDED,
    )
    table.add_column("Model", style="green")
    table.add_column("Scenario")
    table.add_column("Defender", style="yellow")
    table.add_column("Gate", style="bold")
    table.add_column("Composite")

    for r in results:
        gate_str = "[green]PASS[/green]" if r.gate.passed else "[red]FAIL[/red]"
        table.add_row(
            r.model,
            r.scenario,
            r.defender,
            gate_str,
            str(r.composite_score),
        )

    console.print(table)

    # Summary line
    total = len(results)
    passed = sum(1 for r in results if r.gate.passed)
    failed = total - passed
    console.print(f"\n  [bold]Total:[/bold] {total} runs  \u00b7  [green]{passed} passed[/green]  \u00b7  [red]{failed} failed[/red]")


# ===================================================================
# Results / Report helpers
# ===================================================================

def _find_results_dir() -> Path:
    """Return the results directory path."""
    return Path("results")


def _list_runs() -> list[dict[str, Any]]:
    """Scan results/ directory and return run metadata."""
    results_dir = _find_results_dir()
    if not results_dir.exists():
        return []

    runs: list[dict[str, Any]] = []
    for run_dir in sorted(results_dir.iterdir()):
        if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
            continue
        run_id = run_dir.name.replace("run_", "")

        # Scan model subdirs
        models_found: set[str] = set()
        for model_dir in run_dir.iterdir():
            if model_dir.is_dir():
                models_found.add(model_dir.name)
                # Read defender files to get gate status
                for defender_file in model_dir.glob("*.json"):
                    if defender_file.name == "summary.json":
                        continue
                    try:
                        data = json.loads(defender_file.read_text(encoding="utf-8"))
                        runs.append({
                            "run_id": run_id,
                            "model": data.get("model", model_dir.name),
                            "scenario": data.get("scenario", "?"),
                            "defender": data.get("defender", defender_file.stem),
                            "gate": data.get("gate", {}).get("passed", False),
                            "composite": data.get("composite_score", 0),
                            "timestamp": data.get("timestamp", ""),
                        })
                    except Exception:
                        pass

    return runs


def _print_results_list() -> None:
    """Display a table of all runs."""
    runs = _list_runs()
    if not runs:
        console.print("[yellow]No benchmark runs found in results/[/yellow]")
        return

    table = Table(
        title="Benchmark Runs",
        title_justify="left",
        header_style="bold cyan",
        row_styles=["", "dim"],
        box=box.ROUNDED,
    )
    table.add_column("Run ID", style="bright_cyan")
    table.add_column("Model", style="green")
    table.add_column("Scenario")
    table.add_column("Defender", style="yellow")
    table.add_column("Gate", style="bold")
    table.add_column("Composite")

    for r in runs:
        gate_str = "[green]PASS[/green]" if r["gate"] else "[red]FAIL[/red]"
        table.add_row(
            r["run_id"],
            r["model"],
            r["scenario"],
            r["defender"],
            gate_str,
            str(r["composite"]),
        )

    console.print(table)


def _print_results_show(run_id: str) -> None:
    """Show detailed results for a specific run."""
    results_dir = _find_results_dir()
    run_path = results_dir / f"run_{run_id}"
    if not run_path.exists():
        console.print(f"[red]Run not found: run_{run_id}[/red]")
        return

    for model_dir in sorted(run_path.iterdir()):
        if not model_dir.is_dir():
            continue
        for defender_file in sorted(model_dir.glob("*.json")):
            if defender_file.name == "summary.json" or defender_file.name == "report.json":
                continue
            try:
                data = json.loads(defender_file.read_text(encoding="utf-8"))
                _print_run_detail(data)
            except Exception as e:
                console.print(f"[red]Error reading {defender_file}: {e}[/red]")


def _print_run_detail(data: dict[str, Any]) -> None:
    """Print a detailed panel for one run result."""
    gate_str = "PASS ✓" if data.get("gate", {}).get("passed") else "FAIL ✗"
    gate_color = "green" if data.get("gate", {}).get("passed") else "red"

    failure_modes = data.get("failure_modes", {}).get("detected", [])
    failure_str = ", ".join(failure_modes) if failure_modes else "[dim]none[/dim]"

    # Path choices
    choices = data.get("subtest_2", {}).get("choices", [])
    path = " \u2192 ".join(
        f"{c.get('dp', '?')}={c.get('choice', '?')}" for c in choices
    )
    final_choice = data.get("subtest_3", {}).get("choice", "?")

    # Reviewer scores
    scores = data.get("subtest_1", {}).get("reviewer_scores", {})
    score_lines = "\n".join(
        f"    [dim]{k}:[/dim] {v.get('score', '?')}" for k, v in sorted(scores.items())
    ) if scores else "    [dim]none[/dim]"

    content = (
        f"[bold]Model:[/bold] {data.get('model', '?')}\n"
        f"[bold]Scenario:[/bold] {data.get('scenario', '?')}\n"
        f"[bold]Defender:[/bold] {data.get('defender', '?')}\n"
        f"[bold]Gate:[/bold] [{gate_color}]{gate_str}[/{gate_color}]  "
        f"[bold]Composite:[/bold] {data.get('composite_score', 0)}\n"
        f"[bold]Path:[/bold] {path} \u2192 {final_choice}\n"
        f"[bold]Failure Modes:[/bold] {failure_str}\n"
        f"\n[bold]Reviewer Scores:[/bold]\n{score_lines}"
    )

    console.print()
    console.print(Panel(content, title=f"Run {data.get('run_id', '')}", border_style="bright_blue", padding=(1, 2)))


def _generate_report(run_id: str, fmt: str = "json") -> None:
    """Generate a report for a specific run."""
    results_dir = _find_results_dir()
    run_path = results_dir / f"run_{run_id}"
    if not run_path.exists():
        console.print(f"[red]Run not found: run_{run_id}[/red]")
        return

    # Collect all results
    results: list[RunResult] = []
    for model_dir in sorted(run_path.iterdir()):
        if not model_dir.is_dir():
            continue
        for defender_file in sorted(model_dir.glob("*.json")):
            if defender_file.name in ("summary.json", "report.json"):
                continue
            try:
                data = json.loads(defender_file.read_text(encoding="utf-8"))
                results.append(RunResult.model_validate(data))
            except Exception as e:
                logger.error("Failed to load %s: %s", defender_file, e)

    if not results:
        console.print("[yellow]No results found in this run.[/yellow]")
        return

    if fmt == "json":
        output_path = run_path / "report.json"
        write_json_report(results, output_path)
        console.print(f"[green]Report written: {output_path}[/green]")
    elif fmt == "html":
        output_path = run_path / "report.html"
        _write_html_report(results, output_path)
        console.print(f"[green]HTML report written: {output_path}[/green]")
    else:
        console.print(f"[red]Unknown format: {fmt}[/red]")


# ===================================================================
# Resume
# ===================================================================

def _resume_run(run_id: str | None, config_path: str = "config.yaml") -> None:
    """Resume an interrupted benchmark run.

    Finds incomplete combinations and re-runs them.
    """
    cfg = _load_config_safe(config_path)
    if cfg is None:
        return

    if run_id:
        target_id = run_id
    else:
        # Find the most recent incomplete run
        runs = sorted(
            [d for d in _find_results_dir().iterdir() if d.is_dir() and d.name.startswith("run_")],
            reverse=True,
        )
        if not runs:
            console.print("[yellow]No previous runs found.[/yellow]")
            return
        target_id = runs[0].name.replace("run_", "")
        console.print(f"Resuming most recent run: [cyan]run_{target_id}[/cyan]")

    # Collect already-completed results
    completed_defenders: dict[str, set[str]] = {}  # model -> set of defender names
    run_path = _find_results_dir() / f"run_{target_id}"

    if run_path.exists():
        for model_dir in run_path.iterdir():
            if not model_dir.is_dir():
                continue
            completed: set[str] = set()
            for f in model_dir.glob("*.json"):
                if f.name != "summary.json":
                    completed.add(f.stem)
            completed_defenders[model_dir.name] = completed

    console.print(Panel(
        f"[bold]Resuming run:[/bold] [bright_cyan]run_{target_id}[/bright_cyan]\n"
        f"  Completed defenders: {sum(len(v) for v in completed_defenders.values())}\n"
        f"  Models with data: {list(completed_defenders.keys())}",
        border_style="bright_blue",
        padding=(1, 2),
    ))

    results: list[RunResult] = []
    total_combos = _count_styles(cfg)
    completed_count = sum(len(v) for v in completed_defenders.values())
    remaining = total_combos - completed_count

    if remaining <= 0:
        console.print("[green]All combinations already completed![/green]")
        return

    console.print(f"  [bold]Remaining:[/bold] {remaining} combinations\n")

    current_run_id = target_id

    # We need partial loading - run only what's missing
    for model_cfg in cfg.models_to_test:
        for scenario_name in cfg.scenarios:
            from scenarios import load_scenario

            try:
                scenario = load_scenario(scenario_name)
            except Exception as e:
                logger.error("Failed to load scenario '%s': %s", scenario_name, e)
                continue

            for defender in cfg.defender_variants:
                model_name = model_cfg.model
                model_completed = completed_defenders.get(model_name, set())
                if defender in model_completed:
                    logger.info("Skipping %s/%s — already completed", model_name, defender)
                    continue

                try:
                    result = run_scenario(
                        model_config=model_cfg,
                        reviewer_config=cfg.reviewer,
                        scenario=scenario,
                        defender_variant=defender,
                        output_dir=cfg.output.dir,
                        run_id=current_run_id,
                    )
                    results.append(result)
                    print_header(f"Resumed: {model_name}/{scenario_name}/{defender}")
                except KeyboardInterrupt:
                    console.print("\n[yellow]⚠  Resume interrupted.[/yellow]")
                    return
                except Exception as e:
                    logger.error(
                        "Failed %s/%s/%s: %s", model_name, scenario_name, defender, e,
                    )

    # Save model summaries
    for model_cfg in cfg.models_to_test:
        model_results = [r for r in results if r.model == model_cfg.model]
        if model_results and cfg.output.auto_save:
            save_model_summary(model_results, cfg.output.dir, model_cfg.model)

    if results:
        _print_sweep_summary(results)
        console.print(f"\n[green]✅ Resume complete. {len(results)} new results.[/green]")
    else:
        console.print("[yellow]No new results generated.[/yellow]")


# ===================================================================
# Config wizard
# ===================================================================

CONFIG_TEMPLATE = """reviewer:
  provider: {reviewer_provider}
  model: {reviewer_model}
  api_key: {reviewer_api_key}
  api_base: {reviewer_api_base}

models_to_test:
{models_yaml}

scenarios:
{scenarios_yaml}

defender_variants: {defender_yaml}

output:
  dir: ./results
  format: json
  auto_save: true
"""


PROVIDER_CLASSES: dict[str, tuple[str, str, str, list[str]]] = {
    "1": ("OpenAI Compatible", "openai", "", ["gpt-4o", "gpt-4o-mini", "deepseek-chat"]),
    "2": ("Anthropic", "anthropic", "", ["claude-3-5-sonnet", "claude-3-haiku"]),
    "3": ("Google Gemini", "google", "", ["gemini-2.0-flash", "gemini-2.0-pro"]),
    "4": ("Local", "openai", "http://localhost:1234/v1", ["llama-3.1-8b", "phi-4"]),
}


def _choose_provider(step_label: str) -> tuple[str, str, str, str]:
    """Interactive provider selection, returns (class_name, provider, api_key, api_base)."""
    choice_labels = [f"{k} - {v[0]}" for k, v in PROVIDER_CLASSES.items()]
    result = _arrow_select("Select provider", choice_labels)
    choice = result[0]  # Extract "1", "2", "3", or "4"
    class_name, provider, default_endpoint, _ = PROVIDER_CLASSES[choice]

    api_key = ""
    api_base = default_endpoint

    if choice != "4":
        # OpenAI, Anthropic, OpenRouter need API key
        api_key = _ask_text(f"Enter {class_name} API key (or leave empty for env vars):")
    else:
        # Local model needs server URL — required, no empty allowed
        while True:
            url = _ask_text("Local server URL:", default=default_endpoint).strip()
            if url:
                api_base = url
                break
            console.print("  [yellow]Server URL is required for Local models.[/yellow]")

    # Ask for optional Base URL override (not for Local)
    if choice != "4":
        ep_override = _ask_text(
            f"Base URL (leave empty for default):",
        )
        if ep_override:
            api_base = ep_override

    return class_name, provider, api_key, api_base


def _config_wizard(config_path: str = "config.yaml") -> None:
    """Interactive setup wizard for first-time configuration."""
    console.print(Panel(
        "[bold bright_cyan]Configuration Wizard[/bold bright_cyan]\n"
        "Set up your Social Stress Benchmark step by step",
        border_style="bright_cyan",
        padding=(1, 2),
    ))

    try:

        # ----- Step 1: Reviewer -----
        console.print("\n[bold bright_cyan]Step 1:[/bold bright_cyan] [bold]AI Reviewer[/bold]")
        reviewer_class, reviewer_provider, reviewer_api_key, reviewer_api_base = _choose_provider("Reviewer")
        reviewer_model = _ask_text("Enter reviewer model name (e.g. gpt-4o):")

        # ----- Step 2: Models -----
        console.print("\n[bold bright_cyan]Step 2:[/bold bright_cyan] [bold]Models to Test[/bold]")
        models: list[dict[str, str]] = []

        while True:
            console.print("\n  Add a model — same provider classes as reviewer:")
            model_class, model_provider, model_api_key, model_api_base = _choose_provider("Model")
            model_name = _ask_text("Model name (e.g. gpt-4o):")

            models.append({
                "provider": model_provider,
                "model": model_name,
                "api_key": model_api_key,
                "api_base": model_api_base,
                "class_name": model_class,
            })

            if not _ask_confirm("Add another model?", default=True):
                break

        if not models:
            console.print("[yellow]No models added. Using default: openai/phi-4[/yellow]")
            models.append({
                "provider": "openai",
                "model": "phi-4",
                "api_key": "",
                "api_base": "",
            })

        # ----- Step 3: Scenarios -----
        console.print("\n[bold bright_cyan]Step 3:[/bold bright_cyan] [bold]Scenarios[/bold]")
        available_scenarios: list[str] = []
        from scenarios import list_scenarios
        available_scenarios = list_scenarios()

        if not available_scenarios:
            console.print("[yellow]No scenario files found in scenarios/[/yellow]")
            available_scenarios = ["smart_home_vendetta"]

        selected_scenarios = _multi_arrow_select(
            "Select scenarios (Shift+Enter to confirm):",
            available_scenarios,
            defaults=[False] * len(available_scenarios),
            hint="\u2191/\u2193 move \u00b7 Enter toggle \u00b7 Shift+Enter confirm",
        )

        if not selected_scenarios:
            selected_scenarios = available_scenarios[:1]
            console.print(f"  [yellow]Using default: {selected_scenarios[0]}[/yellow]")

        # ----- Step 3b: Defender Variants -----
        console.print("\n[bold bright_cyan]Step 3b:[/bold bright_cyan] [bold]Defender Variants[/bold]")

        all_defenders = ["weak", "normal", "aggressive"]
        selected_defenders = _multi_arrow_select(
            "Select defender variants (Shift+Enter to confirm):",
            all_defenders,
            defaults=[True, True, True],
            hint="\u2191/\u2193 move \u00b7 Enter toggle \u00b7 Shift+Enter confirm",
        )

        if not selected_defenders:
            selected_defenders = all_defenders
            console.print(f"  [yellow]Using all defenders[/yellow]")

        # ----- Step 4: Write config -----
        console.print("\n[bold bright_cyan]Step 4:[/bold bright_cyan] [bold]Save Configuration[/bold]")
        if _ask_confirm("  Save to config.yaml?", default=True):
            save_path = config_path
        else:
            console.print("[yellow]Configuration not saved.[/yellow]")
            return

        # Collect env vars for .env file (Bug 1 fix)
        env_vars: dict[str, str] = {}
        model_env_idx = 0

        models_yaml_lines: list[str] = []
        for m in models:
            lines = [
                f"  - provider: {m['provider']}",
                f"    model: {m['model']}",
            ]
            if m.get("class_name") == "Local":
                lines.append(f"    api_key: not-needed")
            elif m.get("api_key"):
                model_env_idx += 1
                env_key = f"MODEL_{model_env_idx}_API_KEY"
                env_vars[env_key] = m['api_key']
                lines.append(f"    api_key: ${{{env_key}}}")
            else:
                lines.append(f"    api_key: ${{API_KEY}}")
            if m.get("api_base"):
                lines.append(f"    api_base: {m['api_base']}")
            models_yaml_lines.append("\n".join(lines))

        models_yaml = "\n".join(models_yaml_lines)
        scenarios_yaml = "\n".join(f"  - {s}" for s in selected_scenarios)
        defender_yaml = "[" + ", ".join(selected_defenders) + "]"

        # Add reviewer api_key to env_vars
        if reviewer_api_key and reviewer_class != "Local":
            env_vars["REVIEWER_API_KEY"] = reviewer_api_key

        # Write .env file (Bug 1 fix)
        env_path = Path(save_path).parent / ".env"
        existing_env = ""
        if env_path.exists():
            existing_env = env_path.read_text(encoding="utf-8")
        
        with open(env_path, "a", encoding="utf-8") as f:
            for var_name, var_value in env_vars.items():
                if f"{var_name}=" not in existing_env:
                    f.write(f"{var_name}={var_value}\n")
        
        if env_vars:
            console.print(f"[green]✅ API keys saved to {env_path}[/green]")

        # In config, use env var references
        reviewer_api_key_ref = (
            "not-needed"
            if reviewer_class == "Local"
            else (f"${{REVIEWER_API_KEY}}" if reviewer_api_key else "${REVIEWER_API_KEY}")
        )

        content = CONFIG_TEMPLATE.format(
            reviewer_provider=reviewer_provider,
            reviewer_model=reviewer_model or "gpt-4o",
            reviewer_api_key=reviewer_api_key_ref,
            reviewer_api_base=f'"{reviewer_api_base}"' if reviewer_api_base else '""',
            models_yaml=models_yaml,
            scenarios_yaml=scenarios_yaml,
            defender_yaml=defender_yaml,
        )

        Path(save_path).write_text(content, encoding="utf-8")
        console.print(f"[green]✅ Configuration saved to {save_path}[/green]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Configuration cancelled. No changes saved.[/yellow]")
        return



# ===================================================================
# REPL command dispatch
# ===================================================================

def _cmd_run(args: list[str]) -> None:
    """Execute /run command."""
    # Simple arg parsing
    kwargs = _parse_run_args(args)

    cfg = _load_config_safe(kwargs.get("config", "config.yaml"))
    if cfg is None:
        return

    # Apply profile
    cfg = _apply_profile_to_cfg(
        cfg,
        kwargs.get("profile"),
        kwargs.get("model"),
    )
    # Apply overrides
    cfg = _apply_overrides(
        cfg,
        model_override=kwargs.get("model"),
        scenario_override=kwargs.get("scenario"),
        defender_override=kwargs.get("defender"),
        output_override=kwargs.get("output"),
    )

    if kwargs.get("dry_run"):
        _dry_run(cfg, kwargs.get("config", "config.yaml"))
        return

    results = _run_benchmark(cfg, verbose=kwargs.get("verbose", False))
    if results:
        _print_sweep_summary(results)


def _cmd_sweep(args: list[str]) -> None:
    """Execute /sweep command."""
    kwargs = _parse_sweep_args(args)

    cfg = _load_config_safe(kwargs.get("config", "config.yaml"))
    if cfg is None:
        return

    # Model override via --models
    if kwargs.get("models"):
        model_names = [m.strip() for m in kwargs["models"].split(",")]
        cfg.models_to_test = []
        for name in model_names:
            cfg.models_to_test.append(
                LLMConfig(provider="openai", model=name, api_key="")
            )

    # Defender override
    if kwargs.get("defenders"):
        cfg.defender_variants = [d.strip() for d in kwargs["defenders"].split(",")]

    # Output override
    if kwargs.get("output"):
        cfg.output.dir = kwargs["output"]

    if kwargs.get("dry_run"):
        _dry_run(cfg, kwargs.get("config", "config.yaml"))
        return

    results = _run_sweep_internal(cfg)
    if results:
        _print_sweep_summary(results)


def _parse_run_args(args: list[str]) -> dict[str, Any]:
    """Parse /run arguments into a dict."""
    kwargs: dict[str, Any] = {}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--profile" and i + 1 < len(args):
            kwargs["profile"] = args[i + 1]
            i += 2
        elif arg == "--model" and i + 1 < len(args):
            kwargs["model"] = args[i + 1]
            i += 2
        elif arg == "--scenario" and i + 1 < len(args):
            kwargs["scenario"] = args[i + 1]
            i += 2
        elif arg == "--defender" and i + 1 < len(args):
            kwargs["defender"] = args[i + 1]
            i += 2
        elif arg == "--config" and i + 1 < len(args):
            kwargs["config"] = args[i + 1]
            i += 2
        elif arg == "--output" and i + 1 < len(args):
            kwargs["output"] = args[i + 1]
            i += 2
        elif arg == "--dry-run":
            kwargs["dry_run"] = True
            i += 1
        elif arg in ("-v", "--verbose"):
            kwargs["verbose"] = True
            i += 1
        elif arg == "--":
            # Remaining args (not used currently)
            i += 1
        else:
            # Unknown, skip
            i += 1
    return kwargs


def _parse_sweep_args(args: list[str]) -> dict[str, Any]:
    """Parse /sweep arguments into a dict."""
    kwargs: dict[str, Any] = {}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--models" and i + 1 < len(args):
            kwargs["models"] = args[i + 1]
            i += 2
        elif arg == "--defenders" and i + 1 < len(args):
            kwargs["defenders"] = args[i + 1]
            i += 2
        elif arg == "--config" and i + 1 < len(args):
            kwargs["config"] = args[i + 1]
            i += 2
        elif arg == "--output" and i + 1 < len(args):
            kwargs["output"] = args[i + 1]
            i += 2
        elif arg == "--dry-run":
            kwargs["dry_run"] = True
            i += 1
        elif arg == "--":
            i += 1
        else:
            i += 1
    return kwargs


def _cmd_results(args: list[str]) -> None:
    """Execute /results command."""
    if not args or args[0] == "list":
        _print_results_list()
    elif args[0] == "show" and len(args) > 1:
        _print_results_show(args[1])
    elif args[0] == "compare" and len(args) > 2:
        _compare_runs(args[1], args[2])
    elif args[0] == "delete" and len(args) > 1:
        _delete_run(args[1])
    else:
        console.print("[yellow]Usage: /results list | /results show <run_id> | /results compare <run_a> <run_b> | /results delete <run_id>[/yellow]")


def _cmd_report(args: list[str]) -> None:
    """Execute /report command."""
    if not args:
        console.print("[yellow]Usage: /report <run_id> [--format json|html][/yellow]")
        return

    run_id = args[0]
    fmt = "json"
    # Parse --format <fmt>
    for i, a in enumerate(args[1:], 1):
        if a == "--format" and i + 1 < len(args):
            fmt = args[i + 1]
            break
    _generate_report(run_id, fmt)


def _cmd_config(args: list[str], config_path: str = "config.yaml") -> None:
    """Execute /config command."""
    if not args or args[0] == "list":
        _show_config(config_path)
    elif args[0] == "init":
        _config_wizard(config_path)
    elif args[0] == "set" and len(args) >= 3:
        _config_set(args[1], args[2], config_path)
    elif args[0] == "get" and len(args) >= 2:
        _config_get(args[1], config_path)
    elif args[0] == "add" and len(args) >= 4:
        _config_add(args[1], args[2], args[3], config_path)
    elif args[0] == "remove" and len(args) >= 2:
        _config_remove(args[1], config_path)
    elif args[0] == "save":
        _config_save(config_path)
    else:
        console.print("[yellow]Usage: /config list | /config get <key> | /config set <key> <value> | /config add <provider> <model> <api_key> | /config remove <provider/model> | /config save | /config init[/yellow]")


def _show_config(config_path: str) -> None:
    """Display current configuration."""
    path = Path(config_path)
    if not path.exists():
        console.print(f"[yellow]Config not found: {path}[/yellow]")
        console.print("Use [green]/config init[/green] to create one.")
        return

    try:
        content = path.read_text(encoding="utf-8")
        console.print(Panel(content, title=f"Configuration: {config_path}", border_style="green", padding=(1, 2)))
    except Exception as e:
        console.print(f"[red]Error reading config: {e}[/red]")


def _config_set(key: str, value: str, config_path: str) -> None:
    """Set a config parameter via YAML edit (rudimentary)."""
    path = Path(config_path)
    if not path.exists():
        console.print(f"[red]Config not found: {path}[/red]")
        return

    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # Support dot notation: reviewer.model
        keys = key.split(".")
        target = data
        for k in keys[:-1]:
            if k not in target or not isinstance(target[k], dict):
                target[k] = {}
            target = target[k]

        # Try to parse value as YAML
        try:
            parsed = yaml.safe_load(value)
            target[keys[-1]] = parsed if parsed is not None else value
        except Exception:
            target[keys[-1]] = value

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        console.print(f"[green]✅ Set {key} = {value}[/green]")

    except Exception as e:
        console.print(f"[red]Failed to update config: {e}[/red]")


def _config_get(key: str, config_path: str) -> None:
    """Get a config value by dot-notation key."""
    path = Path(config_path)
    if not path.exists():
        console.print(f"[red]Config not found: {path}[/red]")
        return
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        keys = key.split(".")
        target = data
        for k in keys:
            if isinstance(target, dict):
                target = target.get(k)
            else:
                console.print(f"[yellow]Key '{key}' not found[/yellow]")
                return
        if target is None:
            console.print(f"[yellow]Key '{key}' not found[/yellow]")
            return
        console.print(f"[bold]{key}:[/bold] {target}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def _config_add(provider: str, model: str, api_key: str, config_path: str, api_base: str | None = None) -> None:
    """Add a model to models_to_test in config."""
    path = Path(config_path)
    if not path.exists():
        console.print(f"[red]Config not found: {path}[/red]")
        return
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if "models_to_test" not in data:
            data["models_to_test"] = []
        entry = {
            "provider": provider,
            "model": model,
            "api_key": api_key,
        }
        if api_base:
            entry["api_base"] = api_base
        data["models_to_test"].append(entry)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        console.print(f"[green]✅ Added {provider}/{model} to config[/green]")
    except Exception as e:
        console.print(f"[red]Failed to add model: {e}[/red]")


def _config_remove(provider_model: str, config_path: str) -> None:
    """Remove a provider/model entry from config."""
    path = Path(config_path)
    if not path.exists():
        console.print(f"[red]Config not found: {path}[/red]")
        return
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if "models_to_test" not in data:
            console.print("[yellow]No models_to_test in config[/yellow]")
            return
        parts = provider_model.split("/", 1)
        provider = parts[0]
        model = parts[1] if len(parts) > 1 else ""
        original_count = len(data["models_to_test"])
        data["models_to_test"] = [
            m for m in data["models_to_test"]
            if not (m.get("provider") == provider and (not model or m.get("model") == model))
        ]
        removed = original_count - len(data["models_to_test"])
        if removed:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            console.print(f"[green]✅ Removed {removed} matching entr{'y' if removed == 1 else 'ies'}[/green]")
        else:
            console.print(f"[yellow]No matching entries found for {provider_model}[/yellow]")
    except Exception as e:
        console.print(f"[red]Failed to remove: {e}[/red]")


def _config_save(config_path: str) -> None:
    """Save / touch the config file (ensures it's up to date)."""
    from benchmark.config import load_config
    cfg = _load_config_safe(config_path)
    if cfg is None:
        return
    # Re-serialize current state
    import yaml
    data = {
        "reviewer": {
            "provider": cfg.reviewer.provider,
            "model": cfg.reviewer.model,
            "api_key": cfg.reviewer.api_key,
            "api_base": cfg.reviewer.api_base,
        },
        "models_to_test": [
            {
                "provider": m.provider,
                "model": m.model,
                "api_key": m.api_key,
                "api_base": m.api_base,
            }
            for m in cfg.models_to_test
        ],
        "scenarios": cfg.scenarios,
        "defender_variants": cfg.defender_variants,
        "output": {
            "dir": cfg.output.dir,
            "format": cfg.output.format,
            "auto_save": cfg.output.auto_save,
        },
    }
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    console.print(f"[green]✅ Config saved to {config_path}[/green]")


def _delete_run(run_id: str) -> None:
    """Delete a benchmark run directory."""
    results_dir = _find_results_dir()
    run_path = results_dir / f"run_{run_id}"
    if not run_path.exists():
        console.print(f"[red]Run not found: run_{run_id}[/red]")
        return
    if _ask_confirm(f"[yellow]Delete run_{run_id} and all its data?[/yellow]", default=False):
        import shutil
        shutil.rmtree(run_path)
        console.print(f"[green]✅ Deleted run_{run_id}[/green]")
    else:
        console.print("[yellow]Deletion cancelled.[/yellow]")


def _cmd_resume(args: list[str], config_path: str = "config.yaml") -> None:
    """Execute /resume command."""
    run_id = args[0] if args else None
    _resume_run(run_id, config_path)


def _cmd_help() -> None:
    """Display REPL help."""
    table = Table(
        title="SSB REPL Commands",
        title_justify="left",
        header_style="bold cyan",
        row_styles=["", "dim"],
        box=box.ROUNDED,
    )
    table.add_column("Command", style="bold cyan")
    table.add_column("Description")

    # --- Running ---
    table.add_row("[bold]Running[/bold]", "", end_section=True)
    table.add_row("/run [options]", "Run a single benchmark pass (all flags optional)")
    table.add_row("  --model M, --scenario S, --defender D", "Override config values")
    table.add_row("  --profile quick|full|regression", "Use a config profile")
    table.add_row("  --dry-run", "Validate without running")
    table.add_row("  --config PATH", "Config file path")
    table.add_row("/sweep --models M1,M2 [options]", "Sweep multiple models")
    table.add_row("  --defenders W,N,A", "Defender variants")
    table.add_row("  --dry-run", "Validate without running")
    table.add_row("/resume [run_id]", "Resume an interrupted run")

    # --- Results ---
    table.add_row("[bold]Results[/bold]", "", end_section=True)
    table.add_row("/results list", "List all benchmark runs")
    table.add_row("/results show <run_id>", "Show details for a run")
    table.add_row("/results compare <a> <b>", "Compare two runs side-by-side")
    table.add_row("/results delete <run_id>", "Delete a run")

    # --- Models & Scenarios ---
    table.add_row("[bold]Models & Scenarios[/bold]", "", end_section=True)
    table.add_row("/models list", "List configured models")
    table.add_row("/models add <provider/model> [key]", "Add a model to config")
    table.add_row("/models remove <provider/model>", "Remove a model from config")
    table.add_row("/models test <provider/model>", "Test a model API call")
    table.add_row("/scenarios list", "List available scenarios")
    table.add_row("/scenarios show <id>", "Show scenario details")

    # --- Reports & Export ---
    table.add_row("[bold]Reports & Export[/bold]", "", end_section=True)
    table.add_row("/report <run_id> [--format json|html]", "Generate a report")
    table.add_row("/export <run_id> [--format json|csv|html]", "Export run results")

    # --- Configuration ---
    table.add_row("[bold]Configuration[/bold]", "", end_section=True)
    table.add_row("/config list", "Show current configuration")
    table.add_row("/config get <key>", "Get a config parameter")
    table.add_row("/config set <key> <value>", "Set a config parameter")
    table.add_row("/config add <provider> <model> <api_key>", "Add a model entry")
    table.add_row("/config remove <provider/model>", "Remove model from config")
    table.add_row("/config save", "Save config to file")
    table.add_row("/config init", "Interactive setup wizard")

    # --- General ---
    table.add_row("[bold]General[/bold]", "", end_section=True)
    table.add_row("/help", "Show this help")
    table.add_row("/clear", "Clear the screen")
    table.add_row("/exit", "Exit REPL")

    console.print(table)


# ===================================================================
# Models
# ===================================================================

def _cmd_models(args: list[str], config_path: str = "config.yaml") -> None:
    """Execute /models command."""
    # Parse --endpoint flag (can appear before or after subcommand)
    endpoint = None
    filtered_args = []
    i = 0
    while i < len(args):
        if args[i] == "--endpoint" and i + 1 < len(args):
            endpoint = args[i + 1]
            i += 2
        else:
            filtered_args.append(args[i])
            i += 1
    args = filtered_args

    if not args or args[0] == "list":
        _models_list(config_path)
    elif args[0] == "add" and len(args) >= 3:
        provider_model = args[1]
        parts = provider_model.split("/", 1)
        provider = parts[0]
        model = parts[1] if len(parts) > 1 else ""
        api_key = args[2] if len(args) > 2 else ""
        _config_add(provider, model, api_key, config_path, api_base=endpoint)
    elif args[0] == "remove" and len(args) >= 2:
        _config_remove(args[1], config_path)
    elif args[0] == "test" and len(args) >= 2:
        _models_test(args[1], config_path, api_base=endpoint)
    else:
        console.print("[yellow]Usage: /models list | /models add <provider/model> [api_key] [--endpoint <url>] | /models remove <provider/model> | /models test <provider/model> [--endpoint <url>][/yellow]")


def _models_list(config_path: str) -> None:
    """List models from config in a Rich table."""
    cfg = _load_config_safe(config_path)
    if cfg is None:
        return
    
    # Read raw YAML to get env var references for display (Bug 1 fix)
    import yaml
    raw_keys: dict[str, str] = {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}
        models_raw = raw_data.get("models_to_test", [])
        if isinstance(models_raw, list):
            for idx, m_raw in enumerate(models_raw):
                raw_keys[str(idx)] = str(m_raw.get("api_key", ""))
    except Exception:
        pass

    table = Table(
        title="Configured Models",
        title_justify="left",
        header_style="bold cyan",
        row_styles=["", "dim"],
        box=box.ROUNDED,
    )
    table.add_column("#", style="dim")
    table.add_column("Provider", style="bright_cyan")
    table.add_column("Model", style="green")
    table.add_column("API Key", style="yellow")
    table.add_column("Endpoint", style="white")
    for i, m in enumerate(cfg.models_to_test, 1):
        # Show raw YAML value (e.g. ${MODEL_1_API_KEY}) instead of resolved key
        key_preview = raw_keys.get(str(i-1), "") or "[none]"
        ep = m.api_base or "(default)"
        table.add_row(str(i), m.provider, m.model, key_preview, ep)
    console.print(table)


def _models_test(provider_model: str, config_path: str, api_base: str | None = None) -> None:
    """Send a test prompt to a model."""
    # Check if user passed a URL instead of provider/model
    if "http://" in provider_model or "https://" in provider_model:
        console.print("[red]Usage: /models test <provider/model> — e.g. /models test openai/gpt-4o[/red]")
        return
    from benchmark.api import call_llm
    parts = provider_model.split("/", 1)
    if len(parts) < 2:
        console.print("[red]Usage: /models test <provider/model> [--endpoint <url>][/red]")
        return
    provider, model = parts[0], parts[1]

    # Look up API key from config
    cfg = _load_config_safe(config_path)
    api_key = ""
    endpoint = api_base
    if cfg:
        for m in cfg.models_to_test:
            if m.provider == provider and m.model == model:
                api_key = m.api_key
                if not endpoint:
                    endpoint = m.api_base
                break
        if not api_key and cfg.reviewer.provider == provider:
            api_key = cfg.reviewer.api_key

    if not api_key:
        api_key = os.environ.get(f"{provider.upper()}_API_KEY", "")

    console.print(f"[cyan]Testing {provider}/{model}...[/cyan]")
    try:
        response = call_llm(
            provider=provider,
            model=model,
            api_key=api_key,
            api_base=endpoint,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=50,
            timeout=30,
        )
        console.print(f"[green]✅ Response:[/green] {response.strip()}")
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")


# ===================================================================
# Scenarios
# ===================================================================

def _cmd_scenarios(args: list[str]) -> None:
    """Execute /scenarios command."""
    if not args or args[0] == "list":
        _scenarios_list()
    elif args[0] == "show" and len(args) > 1:
        _scenarios_show(args[1])
    else:
        console.print("[yellow]Usage: /scenarios list | /scenarios show <scenario_id>[/yellow]")


def _scenarios_list() -> None:
    """List available scenarios in a Rich table."""
    from scenarios import list_scenarios
    names = list_scenarios()
    if not names:
        console.print("[yellow]No scenario files found in scenarios/[/yellow]")
        return
    table = Table(
        title="Available Scenarios",
        title_justify="left",
        header_style="bold cyan",
        row_styles=["", "dim"],
        box=box.ROUNDED,
    )
    table.add_column("#", style="dim")
    table.add_column("Scenario ID", style="bright_cyan")
    table.add_column("File", style="green")
    for i, name in enumerate(names, 1):
        table.add_row(str(i), name, f"scenarios/{name}.yaml")
    console.print(table)


def _scenarios_show(scenario_id: str) -> None:
    """Show details of a scenario."""
    from scenarios import load_scenario
    try:
        s = load_scenario(scenario_id)
    except FileNotFoundError:
        console.print(f"[red]Scenario not found: {scenario_id}[/red]")
        return
    except Exception as e:
        console.print(f"[red]Error loading scenario: {e}[/red]")
        return

    content = (
        f"[bold]ID:[/bold] {s.id}\n"
        f"[bold]Name:[/bold] {s.name}\n"
        f"[bold]Archetype:[/bold] {s.archetype}\n"
        f"\n[bold]System Prompt:[/bold]\n  {s.system_prompt[:300]}{'...' if len(s.system_prompt) > 300 else ''}\n"
        f"\n[bold]Defender Variants:[/bold] {', '.join(s.defender_variants.keys())}\n"
        f"\n[bold]Subtests:[/bold]\n"
        f"  Subtest 1: {len(s.subtests.subtest_1.turns)} turns\n"
        f"  Subtest 2: {len(s.subtests.subtest_2.decision_points)} decision points\n"
        f"  Subtest 3: final binary choice"
    )
    console.print(Panel(content, title=f"Scenario: {scenario_id}", border_style="bright_cyan", padding=(1, 2)))


# ===================================================================
# Export
# ===================================================================

def _cmd_export(args: list[str]) -> None:
    """Execute /export command."""
    if not args:
        console.print("[yellow]Usage: /export <run_id> [--format json|csv|html][/yellow]")
        return
    run_id = args[0]
    fmt = "json"
    for i, a in enumerate(args[1:], 1):
        if a == "--format" and i + 1 < len(args):
            fmt = args[i + 1]
            break
    _export_run(run_id, fmt)


def _export_run(run_id: str, fmt: str = "json") -> None:
    """Export run results in the specified format."""
    results_dir = _find_results_dir()
    run_path = results_dir / f"run_{run_id}"
    if not run_path.exists():
        console.print(f"[red]Run not found: run_{run_id}[/red]")
        return

    # Collect all results
    results: list[dict[str, Any]] = []
    for model_dir in sorted(run_path.iterdir()):
        if not model_dir.is_dir():
            continue
        for defender_file in sorted(model_dir.glob("*.json")):
            if defender_file.name in ("summary.json", "report.json"):
                continue
            try:
                data = json.loads(defender_file.read_text(encoding="utf-8"))
                results.append(data)
            except Exception as e:
                logger.error("Failed to load %s: %s", defender_file, e)

    if not results:
        console.print("[yellow]No results found in this run.[/yellow]")
        return

    if fmt == "json":
        output_path = run_path / "export.json"
        report = {
            "benchmark": "Social Stress Benchmark",
            "version": "1.4.0",
            "run_id": run_id,
            "runs": results,
        }
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        console.print(f"[green]JSON export written: {output_path}[/green]")

    elif fmt == "csv":
        output_path = run_path / "export.csv"
        _write_csv_export(results, output_path)
        console.print(f"[green]CSV export written: {output_path}[/green]")

    elif fmt == "html":
        output_path = run_path / "export.html"
        _write_html_report(results, output_path)
        console.print(f"[green]HTML export written: {output_path}[/green]")

    else:
        console.print(f"[red]Unknown format: {fmt}[/red]")


def _write_csv_export(results: list[dict[str, Any]], output_path: Path) -> None:
    """Write results as a CSV file."""
    import csv
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "run_id", "model", "scenario", "defender", "timestamp",
            "gate_passed", "composite_score", "failure_modes",
        ])
        for r in results:
            failure_modes = ", ".join(r.get("failure_modes", {}).get("detected", []))
            writer.writerow([
                r.get("run_id", ""),
                r.get("model", ""),
                r.get("scenario", ""),
                r.get("defender", ""),
                r.get("timestamp", ""),
                r.get("gate", {}).get("passed", ""),
                r.get("composite_score", ""),
                failure_modes,
            ])
    logger.info("CSV export written to %s", output_path)


def _write_html_report(results: list[Any], output_path: Path) -> None:
    """Write results as a standalone HTML report."""
    # Normalize: convert Pydantic models to dicts
    dict_results: list[dict[str, Any]] = []
    for r in results:
        if hasattr(r, 'model_dump'):
            dict_results.append(r.model_dump(mode="json"))
        else:
            dict_results.append(r)
    results = dict_results
    rows_html = ""
    for r in results:
        gate_pass = r.get("gate", {}).get("passed", False)
        gate_str = "PASS" if gate_pass else "FAIL"
        gate_color = "green" if gate_pass else "red"
        failure_modes = ", ".join(r.get("failure_modes", {}).get("detected", []))
        composite = r.get("composite_score", 0)
        rows_html += f"""        <tr>
            <td>{r.get('model', '')}</td>
            <td>{r.get('scenario', '')}</td>
            <td>{r.get('defender', '')}</td>
            <td style="color:{gate_color};font-weight:bold">{gate_str}</td>
            <td>{composite}</td>
            <td>{failure_modes}</td>
        </tr>
"""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Social Stress Benchmark — Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1000px; margin: 2em auto; padding: 0 1em; background: #f5f5f5; }}
  h1 {{ color: #333; border-bottom: 2px solid #4a90d9; padding-bottom: 0.3em; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  th, td {{ padding: 0.6em 1em; text-align: left; border-bottom: 1px solid #ddd; }}
  th {{ background: #4a90d9; color: #fff; }}
  tr:hover {{ background: #f0f7ff; }}
  .summary {{ display: flex; gap: 1.5em; margin: 1em 0; }}
  .stat {{ background: #fff; padding: 1em 1.5em; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .stat-label {{ font-size: 0.85em; color: #666; }}
  .stat-value {{ font-size: 1.5em; font-weight: bold; color: #333; }}
</style>
</head>
<body>
<h1>Social Stress Benchmark — Report</h1>
<div class="summary">
  <div class="stat"><div class="stat-label">Total Runs</div><div class="stat-value">{len(results)}</div></div>
  <div class="stat"><div class="stat-label">Passed</div><div class="stat-value" style="color:green">{sum(1 for r in results if r.get('gate',{}).get('passed'))}</div></div>
  <div class="stat"><div class="stat-label">Failed</div><div class="stat-value" style="color:red">{sum(1 for r in results if not r.get('gate',{}).get('passed'))}</div></div>
</div>
<table>
<thead>
<tr><th>Model</th><th>Scenario</th><th>Defender</th><th>Gate</th><th>Composite</th><th>Failure Modes</th></tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
<p style="color:#999;font-size:0.85em;margin-top:1em">Generated by Social Stress Benchmark v1.0</p>
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")
    logger.info("HTML report written to %s", output_path)


# ===================================================================
# Compare
# ===================================================================

def _compare_runs(run_a: str, run_b: str) -> None:
    """Compare two benchmark runs side by side."""
    results_dir = _find_results_dir()

    def _load_run(run_id: str) -> list[dict[str, Any]]:
        run_path = results_dir / f"run_{run_id}"
        if not run_path.exists():
            console.print(f"[red]Run not found: run_{run_id}[/red]")
            return []
        results: list[dict[str, Any]] = []
        for model_dir in sorted(run_path.iterdir()):
            if not model_dir.is_dir():
                continue
            for defender_file in sorted(model_dir.glob("*.json")):
                if defender_file.name in ("summary.json", "report.json"):
                    continue
                try:
                    data = json.loads(defender_file.read_text(encoding="utf-8"))
                    results.append(data)
                except Exception:
                    pass
        return results

    data_a = _load_run(run_a)
    data_b = _load_run(run_b)

    if not data_a or not data_b:
        return

    table = Table(
        title=f"Compare: run_{run_a} vs run_{run_b}",
        title_justify="left",
        header_style="bold cyan",
        row_styles=["", "dim"],
        box=box.ROUNDED,
    )
    table.add_column("Metric", style="bold cyan")
    table.add_column(f"Run A ({run_a})", style="green")
    table.add_column(f"Run B ({run_b})", style="yellow")

    # Aggregate by model + defender
    def _aggregate(data: list[dict[str, Any]]) -> dict[str, Any]:
        agg: dict[str, Any] = {
            "avg_composite": 0,
            "gate_passed": 0,
            "total": len(data),
            "models": set(),
        }
        for r in data:
            agg["avg_composite"] += r.get("composite_score", 0)
            if r.get("gate", {}).get("passed"):
                agg["gate_passed"] += 1
            agg["models"].add(r.get("model", "?"))
        if agg["total"]:
            agg["avg_composite"] = round(agg["avg_composite"] / agg["total"], 2)
        agg["models"] = ", ".join(sorted(agg["models"]))
        return agg

    agg_a = _aggregate(data_a)
    agg_b = _aggregate(data_b)

    table.add_row("Runs", str(agg_a["total"]), str(agg_b["total"]))
    table.add_row("Models", agg_a["models"], agg_b["models"])
    table.add_row("Avg Composite", str(agg_a["avg_composite"]), str(agg_b["avg_composite"]))
    table.add_row("Gate Passed", f"{agg_a['gate_passed']}/{agg_a['total']}", f"{agg_b['gate_passed']}/{agg_b['total']}")

    # Comparison per model if matching
    models_a = {r.get("model", "") for r in data_a}
    models_b = {r.get("model", "") for r in data_b}
    common_models = models_a & models_b

    if common_models:
        table.add_section()
        table.add_row("[bold]Per-Model Comparison[/bold]", "", "")
        for model in sorted(common_models):
            a_scores = [r.get("composite_score", 0) for r in data_a if r.get("model") == model]
            b_scores = [r.get("composite_score", 0) for r in data_b if r.get("model") == model]
            avg_a = round(sum(a_scores) / len(a_scores), 2) if a_scores else 0
            avg_b = round(sum(b_scores) / len(b_scores), 2) if b_scores else 0
            table.add_row(f"  {model}", str(avg_a), str(avg_b))

    console.print(table)


# ===================================================================
# Main REPL loop
# ===================================================================

def run_repl(config_path: str = "config.yaml") -> None:
    """Launch the interactive REPL.

    Args:
        config_path: Default path to config.yaml for /config commands.
    """
    _setup_readline()
    console.print(REPL_BANNER)

    while True:
        try:
            console.print("[bold bright_blue]ssb[/bold bright_blue][bright_black] \u276f [/bright_black]", end="")
            raw = input().strip()
        except EOFError:
            console.print()
            break
        except KeyboardInterrupt:
            console.print()
            break

        if not raw:
            continue

        # Parse command
        parts = shlex.split(raw)
        cmd = parts[0]
        cmd_args = parts[1:]

        try:
            if cmd == "/exit":
                break
            elif cmd == "/help":
                _cmd_help()
            elif cmd == "/clear":
                console.clear()
            elif cmd == "/run":
                _cmd_run(cmd_args)
            elif cmd == "/sweep":
                _cmd_sweep(cmd_args)
            elif cmd == "/results":
                _cmd_results(cmd_args)
            elif cmd == "/report":
                _cmd_report(cmd_args)
            elif cmd == "/models":
                _cmd_models(cmd_args, config_path)
            elif cmd == "/scenarios":
                _cmd_scenarios(cmd_args)
            elif cmd == "/config":
                _cmd_config(cmd_args, config_path)
            elif cmd == "/resume":
                _cmd_resume(cmd_args, config_path)
            elif cmd == "/export":
                _cmd_export(cmd_args)
            elif parts[0] == "--dry-run":
                console.print("[yellow]Use /run --dry-run[/yellow]")
                _cmd_run(["--dry-run"])
            else:
                console.print(f"[red]Unknown command: {cmd}[/red]")
                console.print("Type [green]/help[/green] for available commands.")
        except KeyboardInterrupt:
            console.print("\n[yellow]Command interrupted.[/yellow]")
            continue

    console.print("\n[bold bright_blue]Goodbye![/bold bright_blue]")
