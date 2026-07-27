"""Add Model dialog — form-based ModalScreen for adding a new LLM model.

Used by the model-selector dialogs when the user picks "➕ Add model".
Returns a dict on save or ``None`` on cancel.

Return value (dict)::
    {"provider": str, "model": str, "api_key": str, "api_base": str}
"""

from __future__ import annotations

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

__all__ = ["AddModelDialog"]


class AddModelDialog(ModalScreen[dict[str, str] | None]):
    """Modal dialog form for adding a new model configuration.

    Fields:
      - Provider (free-text, required)
      - Model (free-text, required)
      - API Key (password field, hidden when provider == "local")
      - Base URL (optional)

    Dismisses with a ``dict`` on successful save, ``None`` on cancel/Escape.
    """

    DEFAULT_CSS = """
    AddModelDialog {
        align: center middle;
    }
    AddModelDialog #dialog {
        border: thick $accent;
        background: $surface;
        width: 50;
        padding: 1 2;
    }
    AddModelDialog #title {
        text-style: bold;
        padding-bottom: 1;
    }
    AddModelDialog .field-label {
        margin-top: 1;
        margin-bottom: 0;
    }
    AddModelDialog Input {
        width: 100%;
        margin-bottom: 0;
    }
    AddModelDialog .button-row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    AddModelDialog .button-row > Button {
        min-width: 12;
    }
    AddModelDialog #error-label {
        color: $error;
        text-style: bold;
        margin-top: 1;
        text-align: center;
        width: 100%;
    }
    """

    def __init__(self, title: str = "Add Model", initial: dict[str, str] | None = None) -> None:
        super().__init__()
        self._dialog_title = title
        self._initial = initial

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._dialog_title, id="title")

            yield Label("Provider", classes="field-label", id="provider_label")
            yield Input(
                id="provider",
                placeholder="e.g. openai, deepseek, local",
            )

            yield Label("Model", classes="field-label", id="model_label")
            yield Input(
                id="model",
                placeholder="e.g. gpt-4o",
            )

            yield Label("API Key", classes="field-label", id="api_key_label")
            yield Input(
                id="api_key",
                placeholder="sk-...",
                password=True,
            )

            yield Label("Base URL", classes="field-label", id="api_base_label")
            yield Input(
                id="api_base",
                placeholder="(optional)",
            )

            with Horizontal(classes="button-row"):
                yield Button("Save", id="save-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn", variant="default")

            yield Static("", id="error-label")

    def on_mount(self) -> None:
        """Focus the provider input and set initial field visibility."""
        if self._initial:
            self.query_one("#provider", Input).value = self._initial.get("provider", "")
            self.query_one("#model", Input).value = self._initial.get("model", "")
            self.query_one("#api_key", Input).value = self._initial.get("api_key", "")
            self.query_one("#api_base", Input).value = self._initial.get("api_base", "")
            # Trigger visibility update for api_key field
            provider_val = self._initial.get("provider", "").strip().lower()
            if provider_val == "local":
                for field_id in ("#api_key_label", "#api_key"):
                    try:
                        self.query_one(field_id).display = False
                    except Exception:
                        pass
        self.query_one("#provider", Input).focus()

    # ------------------------------------------------------------------
    # Provider-dependent field toggling
    # ------------------------------------------------------------------

    @on(Input.Changed, "#provider")
    def _on_provider_changed(self, event: Input.Changed) -> None:
        """Hide API key field when provider is 'local'."""
        is_local = event.value.strip().lower() == "local"
        for field_id in ("#api_key_label", "#api_key"):
            try:
                self.query_one(field_id).display = not is_local
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    @on(Button.Pressed, "#save-btn")
    def _on_save(self) -> None:
        """Validate fields and dismiss with model dict."""
        provider = self.query_one("#provider", Input).value.strip()
        model = self.query_one("#model", Input).value.strip()
        api_key = self.query_one("#api_key", Input).value.strip()
        api_base = self.query_one("#api_base", Input).value.strip()

        errors: list[str] = []
        if not provider:
            errors.append("Provider is required.")
        if not model:
            errors.append("Model name is required.")
        if provider.lower() != "local" and not api_key:
            errors.append("API key is required (unless provider is \"local\").")

        if errors:
            self.query_one("#error-label", Static).update("  ".join(errors))
            return

        self.dismiss({
            "provider": provider,
            "model": model,
            "api_key": api_key if provider.lower() != "local" else "not-needed",
            "api_base": api_base,
        })

    @on(Button.Pressed, "#cancel-btn")
    def _on_cancel(self) -> None:
        """Dismiss without returning a value."""
        self.dismiss(None)

    # ------------------------------------------------------------------
    # Keyboard handler
    # ------------------------------------------------------------------

    def on_key(self, event: events.Key) -> None:
        """Handle Escape — dismiss with ``None``."""
        if event.key == "escape":
            event.stop()
            self.dismiss(None)
