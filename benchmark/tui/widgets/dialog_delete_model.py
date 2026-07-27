"""Delete Model dialog — two-stage ModalScreen for removing an LLM model.

Used when the user picks "🗑 Delete model" in the model selector.
Stage 1 shows all configured models. Stage 2 confirms the deletion.

Returns the model ID (``str``) to delete, or ``None`` if cancelled.
"""

from __future__ import annotations

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, OptionList, Static
from textual.widgets.option_list import Option

__all__ = ["DeleteModelDialog"]


class DeleteModelDialog(ModalScreen[str | None]):
    """Two-stage modal dialog for deleting a model.

    Stage 1 — model list:
        Shows all configured models (★ marks the reviewer).
        Arrow keys to navigate, Enter to select.

    Stage 2 — confirmation:
        Yes/No OptionList. Arrow keys + Enter.

    Escape dismisses with ``None`` (cancel).
    """

    DEFAULT_CSS = """
    DeleteModelDialog {
        align: center middle;
    }
    DeleteModelDialog #dialog {
        border: thick $accent;
        background: $surface;
        width: 48;
        padding: 1 2;
    }
    DeleteModelDialog #title {
        text-style: bold;
        padding-bottom: 1;
    }
    DeleteModelDialog #stage-default {
        display: block;
    }
    DeleteModelDialog #stage-confirm {
        display: none;
    }
    DeleteModelDialog #model-hint {
        margin-bottom: 1;
        color: $text-muted;
    }
    DeleteModelDialog OptionList {
        height: 1fr;
        border: none;
    }
    DeleteModelDialog OptionList > .option-list--option-highlighted {
        background: $accent;
        color: $text;
        text-style: bold;
    }
    DeleteModelDialog #confirm-label {
        margin-bottom: 1;
    }
    DeleteModelDialog #confirm-warning {
        color: $text-muted;
        margin-bottom: 1;
    }
    DeleteModelDialog Button {
        margin-top: 1;
    }
    DeleteModelDialog #error-label {
        color: $error;
        text-style: bold;
        margin-top: 1;
        text-align: center;
        width: 100%;
    }
    """

    def __init__(
        self,
        models: list[tuple[str, str]],
        reviewer_key: str,
    ) -> None:
        super().__init__()
        self._models = models
        # Strip any ★ prefix in case reviewer_key came via on_pick
        self._reviewer_key = reviewer_key.lstrip("★ ")
        self._selected_model_id: str | None = None
        self._selected_display: str = ""

    # ------------------------------------------------------------------
    # Stage 1 — model list
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Delete Model", id="title")

            # ── Stage 1: pick a model ──
            with Vertical(id="stage-default"):
                yield Label(
                    "Select model to delete:", id="model-hint"
                )
                option_list = OptionList(id="model-list")
                for _key, display in self._models:
                    option_list.add_option(Option(display, id=_key))
                yield option_list
                yield Button("Cancel", id="cancel-btn", variant="default")
                yield Static("", id="error-label")

            # ── Stage 2: confirm ──
            with Vertical(id="stage-confirm"):
                yield Label("", id="confirm-label")
                yield Label(
                    "This cannot be undone.", id="confirm-warning"
                )
                confirm_list = OptionList(id="confirm-list")
                confirm_list.add_option(
                    Option("Yes, delete", id="__yes__")
                )
                confirm_list.add_option(
                    Option("No, keep it", id="__no__")
                )
                yield confirm_list

    def on_mount(self) -> None:
        """Focus the model list so the user can navigate immediately."""
        self.query_one("#model-list", OptionList).focus()

    # ------------------------------------------------------------------
    # Stage 1 handlers
    # ------------------------------------------------------------------

    @on(OptionList.OptionSelected, "#model-list")
    def _on_model_selected(self, event: OptionList.OptionSelected) -> None:
        """Validate selection and advance to confirmation stage."""
        event.stop()
        model_id = event.option_id
        if model_id is None:
            return

        # Find display name for this model
        display = model_id
        for _key, _disp in self._models:
            if _key == model_id:
                display = _disp
                break

        # Block reviewer deletion
        if model_id == self._reviewer_key:
            self.query_one("#error-label", Static).update(
                "Cannot delete the reviewer model — use Ctrl+O to select a different one"
            )
            return

        # Don't allow deleting the last non-reviewer model
        deletable_count = sum(
            1 for _key, _disp in self._models if _key != self._reviewer_key
        )
        if deletable_count <= 1:
            self.query_one("#error-label", Static).update(
                "Cannot delete the last remaining model — at least one model must be configured"
            )
            return

        # Clear any previous error
        self.query_one("#error-label", Static).update("")

        self._selected_model_id = model_id
        self._selected_display = display

        # Switch to stage 2
        self._show_stage("confirm")

        # Update confirm label
        self.query_one("#confirm-label", Label).update(
            f"Delete [bold]{display}[/bold]?"
        )

        # Focus the confirm list
        self.query_one("#confirm-list", OptionList).focus()

    @on(Button.Pressed, "#cancel-btn")
    def _on_cancel(self) -> None:
        """Dismiss without returning a value."""
        self.dismiss(None)

    # ------------------------------------------------------------------
    # Stage 2 handlers
    # ------------------------------------------------------------------

    @on(OptionList.OptionSelected, "#confirm-list")
    def _on_confirm_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        """Handle Yes/No selection."""
        event.stop()
        if event.option_id == "__yes__":
            self.dismiss(self._selected_model_id)
        elif event.option_id == "__no__":
            self._show_stage("default")
            self.query_one("#model-list", OptionList).focus()

    # ------------------------------------------------------------------
    # Stage visibility helper
    # ------------------------------------------------------------------

    def _show_stage(self, stage: str) -> None:
        """Swap visibility between stage-default and stage-confirm."""
        self.query_one("#stage-default").display = (
            stage == "default"
        )
        self.query_one("#stage-confirm").display = (
            stage == "confirm"
        )

    # ------------------------------------------------------------------
    # Keyboard handler
    # ------------------------------------------------------------------

    def on_key(self, event: events.Key) -> None:
        """Handle Escape — dismiss with ``None``."""
        if event.key == "escape":
            event.stop()
            self.dismiss(None)
