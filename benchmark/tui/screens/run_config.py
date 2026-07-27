"""Run configuration screen — select profile/scenarios/subtests and model.

Layout:
  ┌─ Header ─────────────────────────────────────────────┐
  │ ┌─ selector-area (2 cols) ─┐  ┌─ sidebar ─────────┐ │
  │ │ ThreeColumnSelector       │  │ Test: model_name  │ │
  │ │ Profiles | Scenarios |    │  │ Rev:  model_name  │ │
  │ │ Subtests                  │  │ Ctrl+M/H to chg   │ │
  │ │                           │  │ Status: ready     │ │
  │ │                           │  │ [Start Benchmark] │ │
  │ └───────────────────────────┘  └───────────────────┘ │
  └─ Footer ─────────────────────────────────────────────┘

Models are selected globally via Ctrl+M (reviewer) and Ctrl+H (test).
"""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Grid
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static
from textual.binding import Binding
from benchmark.config import LLMConfig
from benchmark.profiles import profile_names
from scenarios import list_scenarios
from benchmark.tui.widgets.three_column_selector import ThreeColumnSelector


class RunConfigScreen(Screen):
    """Main run configuration screen where users set up a benchmark run."""

    @staticmethod
    def _project_root() -> Path:
        """Resolve the project root from this module's file location."""
        this_file = Path(__file__).resolve()
        root = this_file.parent.parent.parent.parent
        if (root / "config.yaml").exists() or (root / "config.example.yaml").exists():
            return root
        return Path.cwd()

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back to menu", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Grid(id="run-config"):
            with Container(id="selector-area"):
                yield ThreeColumnSelector(
                    profiles=profile_names(),
                    scenarios=list_scenarios(),
                    subtests=["subtest_1", "subtest_2", "subtest_3"],
                    id="selector",
                )
            with Container(id="sidebar"):
                yield Label("Current Models", classes="sidebar-title")
                yield Static("", id="model-info", classes="status-bar")
                yield Label("Selection", classes="sidebar-title")
                yield Static(
                    "Choose a profile or scenarios",
                    id="status-display",
                    classes="status-bar",
                )
                yield Button("Start Benchmark", id="start-button", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        """Show current model selection from app-level state."""
        self._refresh_model_info()

    def on_screen_resume(self) -> None:
        """Refresh when returning to this screen (models may have changed)."""
        self._refresh_model_info()

    # ------------------------------------------------------------------
    # Model info helpers
    # ------------------------------------------------------------------

    def _refresh_model_info(self) -> None:
        """Update the model info display from app state."""
        app = self.app
        test = getattr(app, "test_model", None) or "—"
        rev = getattr(app, "reviewer_model", None) or "—"
        info = self.query_one("#model-info", Static)
        info.update(
            f"Test model: [bold]{test}[/bold]\n"
            f"Reviewer:   [bold]{rev}[/bold]\n"
            "[dim]Ctrl+O reviewer · Ctrl+T test model[/dim]"
        )

    # ------------------------------------------------------------------
    # Status display helpers
    # ------------------------------------------------------------------

    def _update_status(self) -> None:
        """Refresh the status display based on current selector state."""
        selector = self.query_one("#selector", ThreeColumnSelector)
        cfg = selector.get_config()
        status = self.query_one("#status-display", Static)

        if cfg["profile"]:
            status.update(f"Profile: [bold]{cfg['profile']}[/bold]")
        elif cfg["scenarios"]:
            n = len(cfg["scenarios"])
            m = len(cfg["subtests"])
            status.update(
                f"{n} scenario(s), {m} subtest(s) selected"
            )
        else:
            status.update("Choose a profile or scenarios")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    @on(ThreeColumnSelector.SelectionChanged)
    def _on_selection_changed(self) -> None:
        """React to selector changes by updating the status bar."""
        self._update_status()

    @on(Button.Pressed, "#start-button")
    def _on_start(self) -> None:
        """Validate the selection and launch the progress screen."""
        selector = self.query_one("#selector", ThreeColumnSelector)
        status = self.query_one("#status-display", Static)
        app = self.app

        cfg = selector.get_config()

        # Validate: at least a profile or scenarios must be selected
        if not cfg["profile"] and not cfg["scenarios"]:
            status.update("[warning]⚠ Choose a profile or scenarios first[/warning]")
            return

        # Validate: a test model must be selected
        test_model_id: str | None = getattr(app, "test_model", None)
        if not test_model_id:
            app.notify("Select a test model via Ctrl+H first", severity="warning")
            return

        # Validate: a reviewer must be selected
        reviewer_model_id: str | None = getattr(app, "reviewer_model", None)
        if not reviewer_model_id:
            app.notify("Select a reviewer via Ctrl+M first", severity="warning")
            return

        # Build model configs from the app-level selections
        # Parse provider/model from the "provider/model" label format
        def _parse_model_label(label: str) -> tuple[str, str] | None:
            parts = label.split("/", 1)
            if len(parts) == 2:
                return (parts[0].strip(), parts[1].strip())
            return None

        test_parts = _parse_model_label(test_model_id)
        rev_parts = _parse_model_label(reviewer_model_id)

        if not test_parts or not rev_parts:
            status.update("[warning]⚠ Invalid model selection[/warning]")
            return

        selected_model = self._resolve_llm_config(app, test_parts[0], test_parts[1])
        reviewer_model = self._resolve_llm_config(app, rev_parts[0], rev_parts[1])

        if selected_model is None:
            status.update("[warning]⚠ Model config not found in settings[/warning]")
            return
        if reviewer_model is None:
            status.update("[warning]⚠ Reviewer config not found in settings[/warning]")
            return

        run_config = {
            "model": selected_model,
            "reviewer": reviewer_model,
            "profile": cfg["profile"],
            "scenarios": cfg["scenarios"],
            "subtests": cfg["subtests"],
            "output_dir": str(RunConfigScreen._project_root() / "results"),
        }

        # Lazy import to avoid circular dependency at module level
        from benchmark.tui.screens.run_progress import RunProgressScreen

        self.app.push_screen(RunProgressScreen(run_config))

    @staticmethod
    def _resolve_llm_config(app, provider: str, model: str) -> LLMConfig | None:
        """Find a full LLMConfig (with api_key/api_base) in app's config by provider+model."""
        full_config = getattr(app, '_config', None)
        if full_config is None:
            try:
                from benchmark.config import load_config
                full_config = load_config("config.yaml")
            except Exception:
                return None

        # Check reviewer first
        if full_config.reviewer.provider == provider and full_config.reviewer.model == model:
            return full_config.reviewer

        # Check models_to_test
        for m in full_config.models_to_test:
            if m.provider == provider and m.model == model:
                return m

        return None
