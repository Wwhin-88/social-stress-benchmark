"""Textual App entry point for the Social Stress Benchmark TUI.

Launched via ``ssb`` (no arguments). Opens a chat-style interface
with slash commands (/run, /results, etc.) and global keybindings.

Global keybindings (priority — work even while typing):
  - :kbd:`Ctrl+O` — select reviewer model
  - :kbd:`Ctrl+T` — select test model
  - :kbd:`Ctrl+P` — show keyboard shortcuts
  - :kbd:`Ctrl+C` — quit
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding

from benchmark.config import load_config
from benchmark.tui.screens.chat import ChatScreen
from benchmark.tui.screens.welcome import WelcomeScreen
from benchmark.tui.widgets.dialog_model_selector import ModelSelectorDialog
from benchmark.tui.widgets.dialog_shortcuts import ShortcutOverlay


class SSBApp(App[None]):
    """Social Stress Benchmark Textual UI.

    Stores session-level model selection accessible by all screens.
    """

    CSS_PATH = "styles.tcss"
    TITLE = "Social Stress Benchmark"

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Session-level model overrides (set via Ctrl+M / Ctrl+H)
        self.reviewer_model: str | None = None
        self.test_model: str | None = None
        # All available model options (populated on mount from config)
        self._model_options: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        """No widgets — each screen manages its own Header/Footer."""
        if False:
            yield

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        """Check config and route to the correct screen."""
        config_path = Path("config.yaml")

        if config_path.exists():
            self._load_models_from_config()
            self.push_screen(ChatScreen())
        else:
            self.push_screen(WelcomeScreen(), self._after_welcome)

    def _after_welcome(self, _result: Any) -> None:
        """Callback after first-run wizard — reload models, show chat."""
        self._load_models_from_config()
        self.push_screen(ChatScreen())

    def _load_models_from_config(self) -> None:
        """Populate model options from config.yaml (deduplicated)."""
        try:
            config = load_config("config.yaml")
            seen: dict[str, str] = {}  # model_id → display_name

            for m in config.models_to_test:
                key = f"{m.provider}/{m.model}"
                seen[key] = key

            r_label = f"{config.reviewer.provider}/{config.reviewer.model}"
            seen[r_label] = f"★ {r_label}"

            self._model_options = list(seen.items())

            if config.models_to_test:
                self.test_model = f"{config.models_to_test[0].provider}/{config.models_to_test[0].model}"
            self.reviewer_model = r_label
        except Exception:
            self._model_options = []

    # ------------------------------------------------------------------
    # Actions (priority keybindings)
    # ------------------------------------------------------------------

    def action_select_reviewer(self) -> None:
        """Ctrl+O — open model selector for reviewer."""
        if not self._model_options:
            self.notify("No models configured", severity="warning")
            return

        def _on_selected(model_id: str | None) -> None:
            if model_id:
                self.reviewer_model = model_id
                self.notify(f"Reviewer → [bold]{model_id}[/bold]")
                self._refresh_chat_status()

        self.push_screen(
            ModelSelectorDialog("Select Reviewer Model", self._model_options),
            _on_selected,
        )

    def action_select_test_model(self) -> None:
        """Ctrl+T — open model selector for test model."""
        if not self._model_options:
            self.notify("No models configured", severity="warning")
            return

        def _on_selected(model_id: str | None) -> None:
            if model_id:
                self.test_model = model_id
                self.notify(f"Test model → [bold]{model_id}[/bold]")
                self._refresh_chat_status()

        self.push_screen(
            ModelSelectorDialog("Select Test Model", self._model_options),
            _on_selected,
        )

    def action_show_shortcuts(self) -> None:
        """Ctrl+P — show keyboard shortcuts overlay."""
        shortcuts: list[tuple[str, str]] = [
            ("Ctrl+O", "Select reviewer model"),
            ("Ctrl+T", "Select test model"),
            ("Ctrl+B", "Benchmark configuration"),
            ("Ctrl+P", "Show this shortcut list"),
            ("Ctrl+C", "Quit application"),
            ("Enter", "Submit command"),
            ("Ctrl+Enter", "New line in input"),
            ("Esc", "Close / go back"),
        ]
        self.push_screen(ShortcutOverlay(shortcuts))

    def _refresh_chat_status(self) -> None:
        """Notify ChatScreen to refresh its status bar."""
        # If ChatScreen is the top screen, call its refresh
        try:
            screen = self.screen
            if hasattr(screen, '_refresh_status'):
                screen._refresh_status()
        except Exception:
            pass


def run_tui() -> None:
    """Entry point: launch the Textual app."""
    app = SSBApp()
    app.run()
