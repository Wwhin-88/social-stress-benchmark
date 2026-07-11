"""Model selection dialog for choosing a model from a list.

Used by both the reviewer model selector and the test model selector.
"""

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

__all__ = ["ModelSelectorDialog"]


class ModelSelectorDialog(ModalScreen[str | None]):
    """Modal dialog for selecting a model from a list.

    Returns the selected model ID (``str``) or ``None`` if cancelled.
    """

    DEFAULT_CSS = """
    ModelSelectorDialog {
        align: center middle;
    }
    ModelSelectorDialog #dialog {
        border: thick $accent;
        background: $surface;
        width: 42;
        padding: 0 1;
    }
    ModelSelectorDialog #title {
        text-style: bold;
    }
    ModelSelectorDialog OptionList {
        height: 1fr;
    }
    """

    def __init__(self, title: str, models: list[tuple[str, str]]) -> None:
        super().__init__()
        self._dialog_title = title
        self._models = models

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._dialog_title, id="title")
            option_list = OptionList(id="model-list")
            for display_name, model_id in self._models:
                option_list.add_option(Option(display_name, id=model_id))
            yield option_list

    def on_mount(self) -> None:
        """Focus the option list so the user can navigate immediately."""
        self.query_one("#model-list", OptionList).focus()

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        """Handle Enter on an option — dismiss with the model ID."""
        event.stop()
        self.dismiss(event.option_id)

    def on_key(self, event: events.Key) -> None:
        """Handle Escape — dismiss with ``None``."""
        if event.key == "escape":
            event.stop()
            self.dismiss(None)
