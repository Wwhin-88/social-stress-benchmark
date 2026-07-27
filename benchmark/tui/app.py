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

import asyncio
import logging
from pathlib import Path
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding

from benchmark.config import Config, load_config
from benchmark.tui.screens.chat import ChatScreen
from benchmark.tui.screens.welcome import WelcomeScreen
from benchmark.tui.widgets.dialog_model_selector import ModelSelectorDialog
from benchmark.tui.widgets.dialog_add_model import AddModelDialog
from benchmark.tui.widgets.dialog_delete_model import DeleteModelDialog
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
        # Suppress Python logging spilling into Textual TUI
        # (logging.basicConfig in cli.py installed a StreamHandler at import time)
        _root = logging.getLogger()
        _root.handlers.clear()
        # Also suppress litellm's own noisy INFO logging
        _lite = logging.getLogger("LiteLLM")
        _lite.handlers.clear()
        _lite.addHandler(logging.NullHandler())
        _lite.setLevel(logging.WARNING)

        super().__init__()

        super().__init__()
        super().__init__()
        # Session-level model overrides (set via Ctrl+O / Ctrl+T)
        self.reviewer_model: str | None = None
        self.test_model: str | None = None
        # Full Config object from config.yaml (for credential lookups)
        self._config: Config | None = None
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
            # No config.yaml — launch first-run wizard
            # User can use config.example.yaml as reference
            self.push_screen(WelcomeScreen(), self._after_welcome)

    def _after_welcome(self, _result: Any) -> None:
        """Callback after first-run wizard — reload models, show chat."""
        self._load_models_from_config()
        self.push_screen(ChatScreen())

    def _load_models_from_config(self) -> None:
        """Populate model options from config.yaml (deduplicated)."""
        try:
            config = load_config("config.yaml")
            self._config = config
            seen: dict[str, str] = {}

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
    # Config helper
    # ------------------------------------------------------------------

    def _add_model_to_config(
        self, model: dict[str, str], target: str
    ) -> None:
        """Append or replace a model in config.yaml.

        Args:
            model: dict with provider, model, api_key, api_base
            target: "reviewer" to replace the reviewer section,
                    "test" to append to models_to_test
        """
        config_path = Path("config.yaml")
        if not config_path.exists():
            self.notify("config.yaml not found", severity="error")
            return

        import yaml as _yaml

        with open(config_path, "r", encoding="utf-8") as f:
            raw = _yaml.safe_load(f) or {}

        if target == "reviewer":
            raw["reviewer"] = {
                "provider": model["provider"],
                "model": model["model"],
                "api_key": model["api_key"],
            }
            if model.get("api_base"):
                raw["reviewer"]["api_base"] = model["api_base"]
        elif target == "test":
            entry: dict[str, str] = {
                "provider": model["provider"],
                "model": model["model"],
                "api_key": model["api_key"],
            }
            if model.get("api_base"):
                entry["api_base"] = model["api_base"]
            raw.setdefault("models_to_test", []).append(entry)

        with open(config_path, "w", encoding="utf-8") as f:
            _yaml.dump(raw, f, default_flow_style=False, sort_keys=False)

        self.notify(
            f"Model [bold]{model['provider']}/{model['model']}[/bold] added"
        )

    def _delete_model_from_config(self, model_id: str) -> bool:
        """Remove a model from config.yaml.

        Args:
            model_id: provider/model string (e.g. "openai/gpt-4o").

        Returns:
            True if model was removed or was not found, False on error.
        """
        config_path = Path("config.yaml")
        if not config_path.exists():
            self.notify("config.yaml not found", severity="error")
            return False

        import yaml as _yaml

        with open(config_path, "r", encoding="utf-8") as f:
            raw = _yaml.safe_load(f) or {}

        # Determine the reviewer key from config
        reviewer = raw.get("reviewer", {})
        reviewer_key = (
            f"{reviewer.get('provider', '')}/{reviewer.get('model', '')}"
        )

        # Block reviewer deletion
        if model_id == reviewer_key:
            self.notify(
                "Cannot delete reviewer — use Ctrl+O to select a different one",
                severity="error",
            )
            return False

        # Remove from models_to_test
        models = raw.get("models_to_test", [])
        raw["models_to_test"] = [
            m
            for m in models
            if f"{m.get('provider', '')}/{m.get('model', '')}" != model_id
        ]

        with open(config_path, "w", encoding="utf-8") as f:
            _yaml.dump(raw, f, default_flow_style=False, sort_keys=False)

        self.notify(f"Model [bold]{model_id}[/bold] removed")
        return True

    # ------------------------------------------------------------------
    # Helpers: open model selector with add-model support
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Helpers: open model selector with add-model support
    # ------------------------------------------------------------------

    def _open_model_selector(
        self, title: str, on_pick: Any, target: str
    ) -> None:
        """Open ModelSelectorDialog and handle add/delete model flows."""

        def _on_selected(model_id: str | None) -> None:
            if model_id == "__add_model__":
                self.push_screen(
                    AddModelDialog(),
                    lambda result: self._add_model_and_reopen(
                        result, title, on_pick, target
                    ),
                )
            elif model_id == "__delete_model__":
                self.push_screen(
                    DeleteModelDialog(
                        self._model_options,
                        self.reviewer_model or "",
                    ),
                    lambda result: self._delete_model_and_reopen(
                        result, title, on_pick, target
                    ),
                )
            elif model_id == "__update_model__":
                # Re-open selector for picking which model to update
                def _pick_for_update(picked_id: str | None) -> None:
                    if picked_id is None:
                        self._open_model_selector(title, on_pick, target)
                        return
                    if picked_id in ("__add_model__", "__delete_model__", "__update_model__"):
                        self.notify("Please select a model to update", severity="warning")
                        self.push_screen(
                            ModelSelectorDialog("Select model to update", self._model_options),
                            _pick_for_update,
                        )
                        return
                    update_target = "reviewer" if picked_id.startswith("★ ") else "test"
                    initial = self._lookup_model_config(picked_id, update_target)
                    if initial is None:
                        self.notify("Model not found in config", severity="error")
                        self._open_model_selector(title, on_pick, target)
                        return
                    self.push_screen(
                        AddModelDialog(title="Update Model", initial=initial),
                        lambda result: self._handle_update_and_reopen(
                            result, picked_id, update_target, title, on_pick, target
                        ),
                    )
                self.push_screen(
                    ModelSelectorDialog("Select model to update", self._model_options),
                    _pick_for_update,
                )
            elif model_id:
                on_pick(model_id)
        self.push_screen(
            ModelSelectorDialog(title, self._model_options),
            _on_selected,
        )

    def _add_model_and_reopen(
        self,
        result: dict[str, str] | None,
        title: str,
        on_pick: Any,
        target: str,
    ) -> None:
        """Handle AddModelDialog result — save then re-open selector."""
        if result is not None:
            self._add_model_to_config(result, target)
            self._load_models_from_config()

        # Re-open model selector (even if user cancelled add-model)
        self._open_model_selector(title, on_pick, target)

    def _delete_model_and_reopen(
        self,
        result: str | None,
        title: str,
        on_pick: Any,
        target: str,
    ) -> None:
        """Handle DeleteModelDialog result — delete then re-open selector."""
        if result is not None:
            self._delete_model_from_config(result)
            self._load_models_from_config()

        # Re-open model selector (even if user cancelled deletion)
        self._open_model_selector(title, on_pick, target)
    def _lookup_model_config(
        self, model_id: str, target: str
    ) -> dict[str, str] | None:
        """Look up a model's raw config from config.yaml (preserving env var refs)."""
        config_path = Path("config.yaml")
        if not config_path.exists():
            return None

        import yaml as _yaml

        with open(config_path, "r", encoding="utf-8") as f:
            raw = _yaml.safe_load(f) or {}

        clean_id = model_id.lstrip("★ ")

        if target == "reviewer":
            r = raw.get("reviewer", {})
            if isinstance(r, dict) and f"{r.get('provider', '')}/{r.get('model', '')}" == clean_id:
                return {
                    "provider": str(r.get("provider", "")),
                    "model": str(r.get("model", "")),
                    "api_key": str(r.get("api_key", "")),
                    "api_base": str(r.get("api_base", "")),
                }
        elif target == "test":
            for m in raw.get("models_to_test", []):
                if isinstance(m, dict) and f"{m.get('provider', '')}/{m.get('model', '')}" == clean_id:
                    return {
                        "provider": str(m.get("provider", "")),
                        "model": str(m.get("model", "")),
                        "api_key": str(m.get("api_key", "")),
                        "api_base": str(m.get("api_base", "")),
                    }

        return None

    def _update_model_in_config(
        self, model: dict[str, str], old_key: str, target: str
    ) -> None:
        """Update an existing model in config.yaml (replace, no duplicates)."""
        config_path = Path("config.yaml")
        if not config_path.exists():
            self.notify("config.yaml not found", severity="error")
            return

        import yaml as _yaml

        with open(config_path, "r", encoding="utf-8") as f:
            raw = _yaml.safe_load(f) or {}

        old_key = old_key.lstrip("★ ")

        new_entry: dict[str, str] = {
            "provider": model["provider"],
            "model": model["model"],
            "api_key": model["api_key"],
        }
        if model.get("api_base"):
            new_entry["api_base"] = model["api_base"]

        if target == "reviewer":
            raw["reviewer"] = new_entry
        elif target == "test":
            models = raw.get("models_to_test", [])
            found = False
            for i, m in enumerate(models):
                if isinstance(m, dict) and f"{m.get('provider', '')}/{m.get('model', '')}" == old_key:
                    models[i] = new_entry
                    found = True
                    break
            if not found:
                models.append(new_entry)
            raw["models_to_test"] = models

        with open(config_path, "w", encoding="utf-8") as f:
            _yaml.dump(raw, f, default_flow_style=False, sort_keys=False)

        self.notify(
            f"Model [bold]{model['provider']}/{model['model']}[/bold] updated"
        )

    def _handle_update_and_reopen(
        self,
        result: dict[str, str] | None,
        old_model_id: str,
        update_target: str,
        title: str,
        on_pick: Any,
        target: str,
    ) -> None:
        """Handle AddModelDialog result from update flow — save then re-open."""
        if result is not None:
            self._update_model_in_config(result, old_model_id, update_target)
            self._load_models_from_config()

        # Re-open the original model selector
        self._open_model_selector(title, on_pick, target)

    # ------------------------------------------------------------------
    # Actions (priority keybindings)
    # ------------------------------------------------------------------

    def action_select_reviewer(self) -> None:
        """Ctrl+O — open model selector for reviewer."""

        def _on_pick(model_id: str) -> None:
            self.reviewer_model = model_id
            self.notify(f"Reviewer → [bold]{model_id}[/bold]")
            self._refresh_chat_status()

        self._open_model_selector("Select Reviewer Model", _on_pick, "reviewer")

    def action_select_test_model(self) -> None:
        """Ctrl+T — open model selector for test model."""

        def _on_pick(model_id: str) -> None:
            self.test_model = model_id
            self.notify(f"Test model → [bold]{model_id}[/bold]")
            self._refresh_chat_status()

        self._open_model_selector("Select Test Model", _on_pick, "test")

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
        try:
            screen = self.screen
            if hasattr(screen, '_refresh_status'):
                screen._refresh_status()
        except Exception:
            pass

    async def _shutdown(self) -> None:
        """Aggressively cancel all workers on Ctrl+C before shutdown."""
        self.workers.cancel_all()
        await asyncio.sleep(0.5)
        await super()._shutdown()


def run_tui() -> None:
    """Entry point: launch the Textual app."""
    app = SSBApp()
    app.run()
