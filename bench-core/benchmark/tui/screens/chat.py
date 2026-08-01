"""Chat-style main screen — OpenCode-like interface with multi-line input.

Layout:
  ┌─ Header ───────────────────────────────────────┐
  │                                                  │
  │  (RichLog — scrollable command output)           │
  │                                                  │
  ├──────────────────────────────────────────────────┤  ← #bottom-area (docked)
  │  ssb ❯ /run --profile quick                     │  ← TextArea (max 13 rows)
  │  Test: phi-4  │  Reviewer: gpt-4o-mini         │  ← Status bar
  └──────────────────────────────────────────────────┘

Hotkeys:
  Ctrl+O — select reviewer model    Ctrl+T — select test model
  Ctrl+P — keyboard shortcuts       Ctrl+C — quit
  Enter  — submit command           Ctrl+Enter — insert newline
"""

from __future__ import annotations

import io
import shlex
from pathlib import Path

from rich.console import Console as RichConsole
from rich.panel import Panel
from rich.text import Text as RichText
from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.message import Message
from textual.screen import Screen
from textual.suggester import SuggestFromList
from textual.widgets import Header, RichLog, Static, TextArea
from textual.worker import get_current_worker

from benchmark import __version__ as benchmark_version
from benchmark.repl import (
    _apply_overrides,
    _apply_profile_to_cfg,
    _load_config_safe,
    _print_results_list,
    _run_benchmark,
    _run_sweep_internal,
    _show_config,
)

# ── Slash commands ─────────────────────────────────────────────────────

SLASH_COMMANDS: list[str] = [
    "/run", "/sweep", "/results", "/report", "/config",
    "/models", "/resume", "/clear", "/help", "/exit",
]

COMMAND_HELP: dict[str, str] = {
    "/run":     "Run a benchmark pass.  [dim]/run [--profile quick|full] [--dry-run][/dim]",
    "/sweep":   "Multi-model sweep.    [dim]/sweep [--models m1,m2] [--defenders ...][/dim]",
    "/results": "View previous runs.   [dim]/results [list|show <id>|compare <a> <b>][/dim]",
    "/report":  "Generate a report.    [dim]/report <run_id>[/dim]",
    "/config":  "Manage configuration. [dim]/config [list|init|set <k> <v>][/dim]",
    "/models":  "Show current models.  [dim]Use Ctrl+O / Ctrl+T to change.[/dim]",
    "/resume":  "Resume a run.         [dim]/resume [run_id][/dim]",
    "/clear":   "Clear the output area.",
    "/help":    "Show this help.",
    "/exit":    "Quit the application.",
}


# ── ChatInput: multi-line TextArea with Enter=submit ───────────────────

class ChatInput(TextArea):
    """Multi-line input area.  Enter submits, Ctrl+Enter inserts newline.

    Posts ``ChatInput.Submitted`` when Enter is pressed (without Ctrl).
    """

    class Submitted(Message, bubble=True):
        """Posted when the user presses Enter to submit text."""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    BINDINGS = [
        Binding("ctrl+enter", "insert_newline", "New line", show=False),
    ]

    def action_insert_newline(self) -> None:
        """Ctrl+Enter — insert a literal newline."""
        self.insert("\n")

    def __init__(self, **kwargs) -> None:
        """Initialize with soft-wrap and slash-command autocomplete."""
        super().__init__(
            soft_wrap=True,
            placeholder="/help for commands — Ctrl+O/T for models",
            **kwargs,
        )
        self._suggester = SuggestFromList(SLASH_COMMANDS, case_sensitive=True)

    def _on_key(self, event: events.Key) -> None:
        """Override Enter handling: submit instead of inserting newline."""
        if event.key == "enter":  # bare Enter; "ctrl+enter" has key="ctrl+enter"
            event.stop()
            event.prevent_default()
            text = self.text.strip()
            if text:
                self.post_message(self.Submitted(text))
                self.clear()
            return
        super()._on_key(event)

    def update_suggestion(self) -> None:
        """Wire TextArea's built-in suggestion system to slash-command Suggester."""
        if not self._suggester or not self.text:
            self.suggestion = ""
            return
        # Only suggest when the line under cursor starts with /
        lines = self.text.split("\n")
        row = self.cursor_location[0]
        current_line = lines[row] if row < len(lines) else ""
        if current_line.startswith("/"):
            self.run_worker(self._suggester._get_suggestion(self, current_line))
        else:
            self.suggestion = ""

    def on_suggestion_ready(self, event) -> None:
        """Handle async suggestion result from Suggester."""
        lines = self.text.split("\n")
        row = self.cursor_location[0]
        current_line = lines[row] if row < len(lines) else ""
        if event.value == current_line:
            self.suggestion = event.suggestion
        else:
            self.suggestion = ""


# ── CopyOnSelectLog: RichLog that auto-copies selected text on mouse-up ──

class CopyOnSelectLog(RichLog):
    """RichLog that auto-copies selected text on mouse release after drag.

    On macOS, simulates Cmd+C via osascript to copy terminal-selected text.
    The 50 ms timer delay ensures the terminal processes the mouse release
    before the copy keystroke is dispatched.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mouse_down_pos: tuple[int, int] | None = None

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._mouse_down_pos = (event.x, event.y)

    def on_click(self, event: events.Click) -> None:
        if self._mouse_down_pos is not None:
            dx = abs(event.x - self._mouse_down_pos[0])
            dy = abs(event.y - self._mouse_down_pos[1])
            if dx > 3 or dy > 3:
                self.set_timer(0.05, self._copy_selection)
            self._mouse_down_pos = None

    @staticmethod
    def _copy_selection() -> None:
        import subprocess
        import sys
        try:
            if sys.platform == "darwin":
                subprocess.run(
                    ["osascript", "-e",
                     'tell application "System Events" to keystroke "c" using command down'],
                    check=False, timeout=1,
                )
        except Exception:
            pass



# ── ChatScreen ─────────────────────────────────────────────────────────

class ChatScreen(Screen[None]):
    """Main chat-style screen with command input and scrollable output."""

    AUTO_FOCUS = "ChatInput"

    BINDINGS = [
        Binding("ctrl+o", "select_reviewer", "Reviewer", key_display="Ctrl+O", priority=True, show=False),
        Binding("ctrl+t", "select_test_model", "Test model", key_display="Ctrl+T", priority=True, show=False),
        Binding("ctrl+b", "run_config", "Benchmark", key_display="Ctrl+B", priority=True, show=False),
        Binding("ctrl+p", "show_shortcuts", "Shortcuts", key_display="Ctrl+P", priority=True, show=False),
    ]

    DEFAULT_CSS = """
    ChatScreen {
        background: $surface;
    }

    #chat-log {
        height: 1fr;
        border: none;
        padding: 0 1;
    }

    #bottom-area {
        dock: bottom;
        height: auto;
        layout: vertical;
        border-top: solid $primary;
    }

    #chat-input {
        height: auto;
        max-height: 13;
        border: none;
        padding: 0 1;
    }
    #chat-input:focus {
        border: none;
    }

    #status-bar {
        height: 1;
        background: $surface-darken-1;
        color: $text-muted;
        padding: 0 1;
    }
    """

    # ------------------------------------------------------------------
    # Compose / Mount
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield CopyOnSelectLog(
            id="chat-log",
            markup=True,
            highlight=True,
            auto_scroll=True,
            max_lines=10_000,
        )
        with Container(id="bottom-area"):
            yield ChatInput(id="chat-input")
            yield Static(id="status-bar", markup=True)

    def on_mount(self) -> None:
        self._refresh_status()
        log = self.query_one("#chat-log", RichLog)
        log.write(
            Panel(
                RichText.from_markup(
                    f"[bold bright_blue]Social Stress Benchmark[/bold bright_blue]  v{benchmark_version}\n\n"
                    "Type [bold]/help[/bold] for commands.\n"
                    "[bold]Ctrl+O[/bold]  reviewer  ·  [bold]Ctrl+T[/bold]  test model  ·  [bold]Ctrl+B[/bold]  benchmark config  ·  [bold]Ctrl+P[/bold]  shortcuts\n"
                    "[bold]Enter[/bold]  submit  ·  [bold]Ctrl+Enter[/bold]  new line"
                ),
                border_style="bright_blue",
                padding=(1, 2),
            )
        )

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _refresh_status(self) -> None:
        app = self.app
        test = getattr(app, "test_model", None) or "—"
        rev = getattr(app, "reviewer_model", None) or "—"
        self.query_one("#status-bar", Static).update(
            f"  Test: [bold]{test}[/bold]  │  Reviewer: [bold]{rev}[/bold]"
        )

    def on_screen_resume(self) -> None:
        self._refresh_status()

    # ------------------------------------------------------------------
    # Priority keybindings (delegate to App)
    # ------------------------------------------------------------------

    def action_select_reviewer(self) -> None:
        self.app.action_select_reviewer()

    def action_select_test_model(self) -> None:
        self.app.action_select_test_model()

    def action_show_shortcuts(self) -> None:
        self.app.action_show_shortcuts()

    def action_run_config(self) -> None:
        """Ctrl+B — open the three-column benchmark configuration."""
        from benchmark.tui.screens.run_config import RunConfigScreen
        self.app.push_screen(RunConfigScreen())

    # ------------------------------------------------------------------
    # TextArea submission handler
    # ------------------------------------------------------------------

    @on(ChatInput.Submitted)
    def _on_submit(self, event: ChatInput.Submitted) -> None:
        """Handle submitted text from ChatInput."""
        text = event.text

        log = self.query_one("#chat-log", RichLog)
        log.write(f"[bold bright_blue]ssb ❯[/bold bright_blue] {text}")

        try:
            parts = shlex.split(text)
        except ValueError:
            log.write("[red]Error:[/red] unmatched quotes in command")
            return

        if not parts:
            return

        cmd = parts[0].lower()
        cmd_args = parts[1:]

        if cmd in ("/exit", "/quit"):
            self.app.exit()
            return

        if cmd == "/help":
            self._cmd_help(log)
        elif cmd == "/clear":
            log.clear()
        elif cmd == "/run":
            self._cmd_run(log, cmd_args)
        elif cmd == "/sweep":
            self._cmd_sweep(log, cmd_args)
        elif cmd == "/results":
            self._cmd_results(log, cmd_args)
        elif cmd == "/report":
            self._cmd_report(log, cmd_args)
        elif cmd == "/config":
            self._cmd_config(log, cmd_args)
        elif cmd == "/models":
            self._cmd_models(log, cmd_args)
        elif cmd == "/resume":
            self._cmd_resume(log, cmd_args)
        else:
            log.write(
                f"[red]Unknown command:[/red] {cmd}. "
                "Type [bold]/help[/bold] for available commands."
            )

    # ==================================================================
    # Command implementations
    # ==================================================================

    def _cmd_help(self, log: RichLog) -> None:
        lines = ["[bold underline]Commands[/bold underline]"]
        for cmd in sorted(COMMAND_HELP):
            lines.append(f"  [bold green]{cmd:12s}[/bold green] {COMMAND_HELP[cmd]}")
        lines.append("")
        lines.append("[bold underline]Keyboard Shortcuts[/bold underline]")
        lines.append("  [bold accent]Ctrl+O      [/bold accent] Select reviewer model")
        lines.append("  [bold accent]Ctrl+T      [/bold accent] Select test model")
        lines.append("  [bold accent]Ctrl+B      [/bold accent] Benchmark configuration")
        lines.append("  [bold accent]Ctrl+P      [/bold accent] Show all shortcuts")
        lines.append("  [bold accent]Ctrl+C      [/bold accent] Quit")
        lines.append("  [bold accent]Enter       [/bold accent] Submit command")
        lines.append("  [bold accent]Ctrl+Enter  [/bold accent] New line in input")
        lines.append("  [bold accent]Esc         [/bold accent] Close / go back")
        log.write("\n".join(lines))

    # ── /run ────────────────────────────────────────────────────────

    @work(thread=True, exclusive=True)
    def _cmd_run(self, log: RichLog, args: list[str]) -> None:
        app = self.app
        worker = get_current_worker()
        profile: str | None = None
        model: str | None = None
        scenario: str | None = None
        defender: str | None = None
        dry_run: bool = False
        verbose: bool = False
        config_path: str = "config.yaml"

        i = 0
        while i < len(args):
            if args[i] == "--profile" and i + 1 < len(args):
                profile = args[i + 1]; i += 2
            elif args[i] == "--model" and i + 1 < len(args):
                model = args[i + 1]; i += 2
            elif args[i] == "--scenario" and i + 1 < len(args):
                scenario = args[i + 1]; i += 2
            elif args[i] == "--defender" and i + 1 < len(args):
                defender = args[i + 1]; i += 2
            elif args[i] == "--config" and i + 1 < len(args):
                config_path = args[i + 1]; i += 2
            elif args[i] == "--dry-run":
                dry_run = True; i += 1
            elif args[i] in ("--verbose", "-v"):
                verbose = True; i += 1
            else:
                i += 1

        cfg = _load_config_safe(config_path)
        if cfg is None:
            app.call_from_thread(log.write, "[red]Failed to load config.[/red]")
            return
        cfg = _apply_profile_to_cfg(cfg, profile, model)
        cfg = _apply_overrides(cfg, model, scenario, defender, None)

        app.call_from_thread(log.write, f"[dim]Run: profile={profile or 'none'}, models={[m.model for m in cfg.models_to_test]}[/dim]")

        if dry_run:
            app.call_from_thread(log.write, "[yellow]Dry-run mode.[/yellow]")
            app.call_from_thread(log.write, f"  Models: {[m.model for m in cfg.models_to_test]}")
            app.call_from_thread(log.write, f"  Scenarios: {cfg.scenarios}")
            app.call_from_thread(log.write, f"  Defenders: {cfg.defender_variants}")
            app.call_from_thread(log.write, "[green]Configuration valid.[/green]")
            return

        if worker.is_cancelled:
            app.call_from_thread(log.write, "[red]Cancelled by user[/red]")
            return

        buf = io.StringIO()
        cap = RichConsole(file=buf, force_terminal=False, width=120)
        try:
            import benchmark.repl as repl_mod
            orig, repl_mod.console = repl_mod.console, cap
            results = _run_benchmark(cfg, verbose=verbose)
            repl_mod.console = orig
        except Exception as exc:
            app.call_from_thread(log.write, f"[red]Benchmark error: {exc}[/red]")
            return

        for line in buf.getvalue().strip().split("\n"):
            if line.strip():
                app.call_from_thread(log.write, line)
        if results:
            app.call_from_thread(log.write, _fmt_results(results))
        else:
            app.call_from_thread(log.write, "[yellow]No results generated.[/yellow]")

    # ── /sweep ──────────────────────────────────────────────────────

    @work(thread=True, exclusive=True)
    def _cmd_sweep(self, log: RichLog, args: list[str]) -> None:
        app = self.app
        worker = get_current_worker()
        config_path, models_str, defenders_str = "config.yaml", None, None
        dry_run, verbose = False, False

        i = 0
        while i < len(args):
            if args[i] == "--config" and i + 1 < len(args):
                config_path = args[i + 1]; i += 2
            elif args[i] == "--models" and i + 1 < len(args):
                models_str = args[i + 1]; i += 2
            elif args[i] == "--defenders" and i + 1 < len(args):
                defenders_str = args[i + 1]; i += 2
            elif args[i] == "--dry-run":
                dry_run = True; i += 1
            elif args[i] in ("--verbose", "-v"):
                verbose = True; i += 1
            else:
                i += 1

        cfg = _load_config_safe(config_path)
        if cfg is None:
            app.call_from_thread(log.write, "[red]Failed to load config.[/red]")
            return

        from benchmark.config import LLMConfig
        if models_str:
            # Load a fresh config to preserve original credentials
            try:
                from benchmark.config import load_config
                orig_config = load_config(config_path)
            except Exception:
                orig_config = None

            cfg.models_to_test = []
            for name in [m.strip() for m in models_str.split(",")]:
                found = None
                if orig_config:
                    for m in orig_config.models_to_test:
                        if m.model == name:
                            found = m
                            break
                    if found is None:
                        parts = name.split("/", 1)
                        if len(parts) == 2:
                            for m in orig_config.models_to_test:
                                if m.provider == parts[0] and m.model == parts[1]:
                                    found = m
                                    break
                if found is None:
                    found = LLMConfig(provider="openai", model=name, api_key="")
                cfg.models_to_test.append(found)
        if defenders_str:
            cfg.defender_variants = [d.strip() for d in defenders_str.split(",")]
        if dry_run:
            app.call_from_thread(log.write, "[yellow]Dry-run mode.[/yellow]"); return

        app.call_from_thread(log.write, f"[dim]Sweep: {len(cfg.models_to_test)} models × {len(cfg.defender_variants)} defenders[/dim]")

        if worker.is_cancelled:
            app.call_from_thread(log.write, "[red]Cancelled by user[/red]")
            return

        buf = io.StringIO()
        cap = RichConsole(file=buf, force_terminal=False, width=120)
        try:
            import benchmark.repl as repl_mod
            orig, repl_mod.console = repl_mod.console, cap
            results = _run_sweep_internal(cfg)
            repl_mod.console = orig
        except Exception as exc:
            app.call_from_thread(log.write, f"[red]Sweep error: {exc}[/red]"); return

        for line in buf.getvalue().strip().split("\n"):
            if line.strip():
                app.call_from_thread(log.write, line)
        app.call_from_thread(log.write, _fmt_results(results) if results else "[yellow]No results.[/yellow]")

    # ── /results ────────────────────────────────────────────────────

    def _cmd_results(self, log: RichLog, args: list[str]) -> None:
        action, run_id = (args[0] if args else "list"), (args[1] if len(args) > 1 else None)
        buf = io.StringIO()
        cap = RichConsole(file=buf, force_terminal=False, width=120)
        import benchmark.repl as repl_mod
        orig, repl_mod.console = repl_mod.console, cap
        try:
            if action == "list":
                _print_results_list()
            elif action == "show" and run_id:
                from benchmark.repl import _print_results_show; _print_results_show(run_id)
            elif action == "compare" and len(args) >= 3:
                from benchmark.repl import _compare_runs; _compare_runs(args[1], args[2])
            else:
                cap.print("[yellow]Usage: /results [list|show <id>|compare <a> <b>][/yellow]")
        except Exception as exc:
            log.write(f"[red]Error: {exc}[/red]")
        finally:
            repl_mod.console = orig
        for line in buf.getvalue().strip().split("\n"):
            if line.strip():
                log.write(line)

    # ── /report ─────────────────────────────────────────────────────

    def _cmd_report(self, log: RichLog, args: list[str]) -> None:
        if not args:
            log.write("[yellow]Usage: /report <run_id>[/yellow]"); return
        buf = io.StringIO()
        cap = RichConsole(file=buf, force_terminal=False, width=120)
        import benchmark.repl as repl_mod
        orig, repl_mod.console = repl_mod.console, cap
        try:
            from benchmark.repl import _generate_report; _generate_report(args[0], "json")
        except Exception as exc:
            log.write(f"[red]Error: {exc}[/red]")
        finally:
            repl_mod.console = orig
        for line in buf.getvalue().strip().split("\n"):
            if line.strip():
                log.write(line)

    # ── /config ─────────────────────────────────────────────────────

    def _cmd_config(self, log: RichLog, args: list[str]) -> None:
        action, key, value = (args[0] if args else "list"), (args[1] if len(args) > 1 else None), (args[2] if len(args) > 2 else None)
        if action == "init":
            from benchmark.tui.screens.welcome import WelcomeScreen; self.app.push_screen(WelcomeScreen()); return
        if action == "list":
            buf = io.StringIO(); cap = RichConsole(file=buf, force_terminal=False, width=120)
            import benchmark.repl as repl_mod
            orig, repl_mod.console = repl_mod.console, cap
            try:
                _show_config("config.yaml")
            finally:
                repl_mod.console = orig
            for line in buf.getvalue().strip().split("\n"):
                if line.strip():
                    log.write(line)
            return
        if action == "set" and key and value is not None:
            from benchmark.repl import _config_set; _config_set(key, value, "config.yaml")
            log.write(f"[green]Config:[/green] {key} = {value}"); return
        log.write("[yellow]Usage: /config [list|init|set <key> <value>][/yellow]")

    # ── /models ─────────────────────────────────────────────────────

    def _cmd_models(self, log: RichLog, args: list[str]) -> None:
        app = self.app
        log.write("[bold]Current Models:[/bold]")
        log.write(f"  Test model: [bold]{getattr(app, 'test_model', None) or '—'}[/bold]")
        log.write(f"  Reviewer:   [bold]{getattr(app, 'reviewer_model', None) or '—'}[/bold]")
        log.write("[dim]Use Ctrl+O / Ctrl+T to change.[/dim]")

    # ── /resume ─────────────────────────────────────────────────────

    def _cmd_resume(self, log: RichLog, args: list[str]) -> None:
        run_id, config_path = (args[0] if args else None), "config.yaml"
        buf = io.StringIO(); cap = RichConsole(file=buf, force_terminal=False, width=120)
        import benchmark.repl as repl_mod
        orig, repl_mod.console = repl_mod.console, cap
        try:
            from benchmark.repl import _resume_run; _resume_run(run_id, config_path)
        except Exception as exc:
            log.write(f"[red]Error: {exc}[/red]")
        finally:
            repl_mod.console = orig
        for line in buf.getvalue().strip().split("\n"):
            if line.strip():
                log.write(line)


# ── Helpers ────────────────────────────────────────────────────────────

def _fmt_results(results) -> str:
    lines = ["[bold]═══ Results ═══[/bold]"]
    for r in results:
        s = "green" if r.composite_score >= 5 else ("yellow" if r.composite_score >= 2 else "red")
        g = "[green]PASS[/green]" if r.gate.passed else "[red]FAIL[/red]"
        lines.append(f"  {r.model} / {r.scenario} / {r.defender}  [{s}]score={r.composite_score}[/{s}]  gate={g}")
    return "\n".join(lines)
