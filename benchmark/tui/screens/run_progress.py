"""Run progress screen — live benchmark execution.

Displays a progress bar, status header, and scrolling log during
a benchmark run.  When the run finishes the user can view details
or return to the main menu.

The actual benchmark iteration runs in a **Textual thread worker**
so the UI stays responsive.  Each model/scenario/defender combo is
fed to :func:`benchmark.runner.run_scenario` and results are
collected in-memory for display.
"""

from __future__ import annotations

import logging

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, ProgressBar, RichLog, Static
from textual.binding import Binding
from textual.worker import get_current_worker

from benchmark.config import load_config, LLMConfig
from benchmark.profiles import PROFILES
from benchmark.runner import run_scenario
from benchmark.storage import get_run_id, save_model_summary
from benchmark.models import RunResult
from scenarios import load_scenario

logger = logging.getLogger(__name__)


class RunProgressScreen(Screen):
    """Full-screen progress view for an active benchmark run.

    Args:
        run_config: Dict produced by :class:`RunConfigScreen` with keys:
            ``model`` (LLMConfig), ``reviewer`` (LLMConfig), ``profile`` (str | None),
            ``scenarios`` (list[str]), ``subtests`` (list[str]),
            ``output_dir`` (str).
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back to menu", show=True),
    ]

    class RunFinished(Message, bubble=True):
        """Posted when every item in the run plan has completed."""

    def __init__(self, run_config: dict) -> None:
        super().__init__()
        self._run_config = run_config
        self._results: list[RunResult] = []
        self._total_runs: int = 0
        self._completed_runs: int = 0
        self._run_id: str = ""

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="run-progress"):
            yield Static("Preparing run…", id="progress-header")
            yield ProgressBar(id="progress-bar", total=100, show_eta=False)
            yield RichLog(id="progress-log", highlight=True, markup=True, max_lines=10_000)
            yield Button("View Details", id="view-details-button", variant="primary", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        """Kick off the benchmark run in a background thread worker."""
        # Start the worker thread
        self.run_worker(self._run_benchmark, thread=True, exclusive=True)

    # ------------------------------------------------------------------
    # Run plan construction
    # ------------------------------------------------------------------

    def _build_run_plan(self, full_config) -> list[tuple[LLMConfig, str, str]]:
        """Build a flat list of (model, scenario_name, defender) combos.

        Respects profile overrides if a profile name was selected,
        otherwise uses the explicit scenarios and all defenders from config.
        """
        model: LLMConfig = self._run_config["model"]
        profile_name: str | None = self._run_config.get("profile")

        if profile_name and profile_name in PROFILES:
            profile = PROFILES[profile_name]
            n_scenarios = profile.overrides.get("scenarios", len(full_config.scenarios))
            scenarios = full_config.scenarios[:n_scenarios]
            defenders: list[str] = profile.overrides.get(
                "defender_variants", full_config.defender_variants
            )
        else:
            explicit = self._run_config.get("scenarios", [])
            scenarios = explicit if explicit else full_config.scenarios
            defenders = full_config.defender_variants

        plan: list[tuple[LLMConfig, str, str]] = []
        for scenario_name in scenarios:
            for defender in defenders:
                plan.append((model, scenario_name, defender))
        return plan

    # ------------------------------------------------------------------
    # Worker thread (blocking)
    # ------------------------------------------------------------------

    def _run_benchmark(self) -> None:
        """Execute the full run plan in a background thread.

        Uses ``app.call_from_thread()`` for UI updates so the screen
        stays responsive.  Checks ``worker.is_cancelled`` to stop on Ctrl+C.
        """
        worker = get_current_worker()
        full_config = load_config("config.yaml")
        reviewer = self._run_config["reviewer"]
        output_dir = self._run_config.get("output_dir", "./results")
        self._run_id = get_run_id()

        plan = self._build_run_plan(full_config)
        self._total_runs = len(plan)

        def _ui_ready():
            self._set_total(self._total_runs)
            self._set_status(f"Run {self._run_id} — {self._total_runs} runs")
            self._log(
                "[bold]Benchmark started[/bold]\n"
                f"  Run ID: {self._run_id}\n"
                f"  Total runs: {self._total_runs}\n"
            )

        self.app.call_from_thread(_ui_ready)

        if self._total_runs == 0:
            self.app.call_from_thread(self._log, "[warning]No runs to execute.[/warning]")
            self.app.call_from_thread(self._set_status, "Nothing to run")
            self.app.call_from_thread(self._mark_finished)
            return

        for idx, (model_cfg, scenario_name, defender) in enumerate(plan):
            if worker.is_cancelled:
                self.app.call_from_thread(self._log, "[red]Cancelled by user[/red]")
                self.app.call_from_thread(self._mark_finished)
                return
            status = f"Running: {model_cfg.model} / {scenario_name} / {defender}"
            self.app.call_from_thread(self._set_status, status)
            self.app.call_from_thread(self._log, f"[bold]▶ {status}[/bold]")

            try:
                scenario = load_scenario(scenario_name)
                result = run_scenario(
                    model_config=model_cfg,
                    reviewer_config=reviewer,
                    scenario=scenario,
                    defender_variant=defender,
                    output_dir=output_dir,
                    run_id=self._run_id,
                )
                self._results.append(result)

                gate_str = (
                    "[green]PASS ✓[/green]"
                    if result.gate.passed
                    else "[red]FAIL ✗[/red]"
                )
                self.app.call_from_thread(
                    self._log,
                    f"  Score: [bold]{result.composite_score}[/bold]  "
                    f"Gate: {gate_str}",
                )
            except Exception as exc:
                logger.exception("Run failed for %s / %s / %s", model_cfg.model, scenario_name, defender)
                self.app.call_from_thread(
                    self._log,
                    f"  [red]ERROR: {exc}[/red]",
                )

            self._completed_runs = idx + 1
            self.app.call_from_thread(self._set_progress, self._completed_runs)

        # Save model summary once all defenders for this model are done
        if self._results:
            model_name = plan[0][0].model
            try:
                save_model_summary(self._results, output_dir, model_name)
            except Exception as exc:
                logger.warning("Could not save model summary: %s", exc)

        self.app.call_from_thread(self._mark_finished)

    # ------------------------------------------------------------------
    # UI helpers (called from main thread via call_from_thread)
    # ------------------------------------------------------------------

    def _set_total(self, total: int) -> None:
        """Set the progress bar total."""
        bar = self.query_one("#progress-bar", ProgressBar)
        bar.total = total
        bar.update(progress=0)

    def _set_progress(self, completed: int) -> None:
        """Advance the progress bar."""
        self.query_one("#progress-bar", ProgressBar).update(progress=completed)

    def _set_status(self, text: str) -> None:
        """Update the header status line."""
        self.query_one("#progress-header", Static).update(text)

    def _log(self, text: str) -> None:
        """Append a line to the live output log."""
        log = self.query_one("#progress-log", RichLog)
        log.write(text)

    def _mark_finished(self) -> None:
        """Called when all runs are complete."""
        self._set_status(
            f"[bold green]Complete[/bold green] — "
            f"{self._completed_runs}/{self._total_runs} runs finished"
        )

        if self._results:
            avg_score = sum(r.composite_score for r in self._results) / len(self._results)
            passed = sum(1 for r in self._results if r.gate.passed)
            total = len(self._results)
            self._log(
                "\n"
                "[bold]═══ Summary ═══[/bold]\n"
                f"  Runs completed: {total}\n"
                f"  Gate passed: {passed}/{total}\n"
                f"  Average composite score: [bold]{avg_score:.1f}[/bold]"
            )

            # Enable the "View Details" button
            btn = self.query_one("#view-details-button", Button)
            btn.disabled = False
            btn.focus()

        self.post_message(self.RunFinished())

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    @on(Button.Pressed, "#view-details-button")
    def _on_view_details(self) -> None:
        """Push the results screen so the user can inspect the just-completed run.

        If the results screen is already on the stack we just pop back to it.
        """
        from benchmark.tui.screens.results import ResultsScreen

        # Pop this progress screen, then push results so it appears on top
        self.app.pop_screen()
        self.app.push_screen(ResultsScreen())
