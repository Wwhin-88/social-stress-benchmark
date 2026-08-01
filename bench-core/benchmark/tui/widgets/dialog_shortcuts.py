"""Compact keyboard-shortcuts overlay dialog.

Dismisses on any keypress, modelled after OpenCode's which-key popup.
Two-column layout: key (left, bold accent) + description (right, muted).
"""

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label

DEFAULT_CSS = """
ShortcutOverlay {
    align: center middle;
}

ShortcutOverlay #dialog {
    border: thick $secondary;
    background: $surface-darken-1;
    width: 50;
    height: auto;
    padding: 1 2;
}

ShortcutOverlay #title {
    text-style: bold;
    width: 1fr;
    content-align: center top;
    padding-bottom: 1;
}

ShortcutOverlay #shortcuts {
    width: 1fr;
    height: auto;
}

ShortcutOverlay #hint {
    color: $text-muted;
    text-style: italic;
    width: 1fr;
    content-align: center bottom;
    padding-top: 1;
}
"""


class ShortcutOverlay(ModalScreen[None]):
    """Compact keyboard-shortcuts overlay that dismisses on any keypress."""

    DEFAULT_CSS = DEFAULT_CSS

    def __init__(self, shortcuts: list[tuple[str, str]]) -> None:
        super().__init__()
        self._shortcuts = shortcuts

    def compose(self) -> ComposeResult:
        """Build the dialog with two-column layout."""
        # Calculate max key width for alignment
        max_key_width = max((len(k) for k, _ in self._shortcuts), default=10)
        # Add some padding
        key_width = max_key_width + 4

        with Vertical(id="dialog"):
            yield Label("Keyboard Shortcuts", id="title")
            with Vertical(id="shortcuts"):
                for key, desc in self._shortcuts:
                    # Pad key to fixed width, then description in muted color
                    padded_key = key.ljust(key_width)
                    yield Label(
                        f"[bold accent]{padded_key}[/bold accent][$text-muted]{desc}[/$text-muted]"
                    )
            yield Label("Press any key to dismiss", id="hint")

    def on_key(self, event: events.Key) -> None:
        """Dismiss the overlay on any keypress."""
        self.dismiss(None)
