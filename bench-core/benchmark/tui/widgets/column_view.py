"""Single-column selectable list with keyboard navigation.

Supports single-select (radio) and multi-select (checkbox) modes.
Emits Selected/Confirmed messages for parent widgets to handle.
"""

from __future__ import annotations

from textual import on
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget

# Sentinel icons — use Unicode to avoid terminal compatibility issues
CHECK_ON = "[✓]"
CHECK_OFF = "[ ]"
CURSOR = "❯"


class ColumnView(Widget, can_focus=True):
    """A scrollable column of selectable items.

    Args:
        title: Column header text.
        items: List of item labels.
        select_mode: ``"single"`` (radio — only one selection) or ``"multi"`` (checkbox).
    """

    DEFAULT_CSS = """
    ColumnView {
        height: 100%;
        border: solid $primary;
        background: $surface;
        padding: 0;
    }
    ColumnView:focus {
        border: solid $accent;
    }
    ColumnView.disabled {
        opacity: 0.5;
        border: dashed $primary;
    }
    ColumnView > .column-title-row {
        height: 1;
        background: $primary;
        color: $text-muted;
        text-style: bold;
        padding: 0 1;
    }
    ColumnView:focus > .column-title-row {
        background: $accent;
        color: $text;
    }
    """

    BINDINGS = [
        Binding("up", "cursor_up", "Move up", show=False),
        Binding("down", "cursor_down", "Move down", show=False),
        Binding("enter", "toggle_item", "Toggle item", show=False),
        Binding("shift+enter", "confirm", "Confirm selection", show=False),
    ]

    class Selected(Message, bubble=True):
        """Emitted when an item is toggled via Enter.

        Attrs:
            item_index: Index of the toggled item.
            column_id: id of the ColumnView.
        """

        def __init__(self, column_view: ColumnView, item_index: int) -> None:
            super().__init__()
            self.column_view = column_view
            self.item_index = item_index

    class Confirmed(Message, bubble=True):
        """Emitted when Shift+Enter is pressed (confirm selection)."""

        def __init__(self, column_view: ColumnView) -> None:
            super().__init__()
            self.column_view = column_view

    highlight_index: reactive[int] = reactive(0, always_update=True)
    disabled: reactive[bool] = reactive(False)

    def __init__(
        self,
        title: str,
        items: list[str],
        select_mode: str = "multi",
        *,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
    ) -> None:
        super().__init__(name=name, id=id)
        self._title = title
        self._items: list[str] = list(items)
        self._select_mode = select_mode  # "single" | "multi"
        self._selected: set[int] = set()
        self._scroll_offset: int = 0
        self.border_title = title

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def items(self) -> list[str]:
        return list(self._items)

    @property
    def selected_items(self) -> list[str]:
        return [self._items[i] for i in sorted(self._selected)]

    @property
    def selected_indices(self) -> set[int]:
        return set(self._selected)

    @property
    def has_selection(self) -> bool:
        return len(self._selected) > 0

    @property
    def select_mode(self) -> str:
        return self._select_mode

    def set_items(self, items: list[str]) -> None:
        """Replace items and reset state."""
        self._items = list(items)
        self._selected.clear()
        self.highlight_index = 0
        self._scroll_offset = 0
        self.refresh(layout=True)

    def reset_selection(self) -> None:
        self._selected.clear()
        self.refresh()

    def set_selected(self, indices: set[int]) -> None:
        """Replace selection with the given indices (respects mode)."""
        if self._select_mode == "single" and len(indices) > 1:
            indices = {next(iter(indices))}
        self._selected = set(indices)
        self.refresh()

    def jump_highlight(self, index: int) -> None:
        """Move highlight to a specific item index."""
        if 0 <= index < len(self._items):
            self.highlight_index = index
            self._scroll_into_view()

    # ------------------------------------------------------------------
    # Watchers
    # ------------------------------------------------------------------

    def watch_highlight_index(self, old: int, new: int) -> None:
        self._scroll_into_view()

    def watch_disabled(self, old: bool, new: bool) -> None:
        if new:
            self.add_class("disabled")
        else:
            self.remove_class("disabled")

    # ------------------------------------------------------------------
    # Actions (key bindings)
    # ------------------------------------------------------------------

    def action_cursor_up(self) -> None:
        if self.disabled:
            return
        if len(self._items) == 0:
            return
        self.highlight_index = (self.highlight_index - 1) % len(self._items)

    def action_cursor_down(self) -> None:
        if self.disabled:
            return
        if len(self._items) == 0:
            return
        self.highlight_index = (self.highlight_index + 1) % len(self._items)

    def action_toggle_item(self) -> None:
        if self.disabled or len(self._items) == 0:
            return
        idx = self.highlight_index

        if self._select_mode == "single":
            # Radio mode: toggle — if already selected, deselect; else replace
            if idx in self._selected:
                self._selected.discard(idx)
            else:
                self._selected = {idx}
        else:
            # Multi mode: toggle
            if idx in self._selected:
                self._selected.discard(idx)
            else:
                self._selected.add(idx)

        self.refresh()
        self.post_message(self.Selected(self, idx))

    def action_confirm(self) -> None:
        """Shift+Enter — confirm and signal parent."""
        if self.disabled:
            return
        self.post_message(self.Confirmed(self))

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self) -> str:
        """Render the item list with highlight and selection indicators."""
        if not self._items:
            if self.disabled:
                return "  (locked by other selection)"
            return "  (no items)"

        # Calculate visible range
        title_height = 1
        content_height = self.size.height - title_height
        if content_height <= 0:
            return ""

        # Scroll offset bounds
        max_offset = max(0, len(self._items) - content_height)
        if self._scroll_offset > max_offset:
            self._scroll_offset = max_offset
        if self._scroll_offset < 0:
            self._scroll_offset = 0

        visible_end = min(len(self._items), self._scroll_offset + content_height)
        lines: list[str] = []

        for i in range(self._scroll_offset, visible_end):
            item = self._items[i]
            highlighted = i == self.highlight_index
            selected = i in self._selected

            check = CHECK_ON if selected else CHECK_OFF
            prefix = CURSOR if highlighted else " "

            if highlighted:
                # Use rich-style markup for reverse video effect
                line = f"[reverse]{prefix}{check} {item}[/reverse]"
            elif selected:
                line = f"[bold green]{prefix}{check} {item}[/bold green]"
            else:
                line = f" {prefix}{check} {item}"

            lines.append(line)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Scrolling
    # ------------------------------------------------------------------

    def _scroll_into_view(self) -> None:
        """Adjust scroll offset so highlighted item is visible."""
        title_height = 1
        content_height = self.size.height - title_height
        if content_height <= 0:
            return

        idx = self.highlight_index
        if idx < self._scroll_offset:
            self._scroll_offset = idx
        elif idx >= self._scroll_offset + content_height:
            self._scroll_offset = idx - content_height + 1

        # Clamp
        max_offset = max(0, len(self._items) - content_height)
        self._scroll_offset = max(0, min(self._scroll_offset, max_offset))
