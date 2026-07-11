"""Main menu screen for the Social Stress Benchmark TUI.

Provides keyboard-navigable menu options:
  - [R] Run Benchmark
  - [V] View Results
  - [C] Configure
  - [H] Help
  - [Q] Quit
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static


# ---------------------------------------------------------------------------
# Menu item descriptor
# ---------------------------------------------------------------------------
class MenuItem:
    """A single menu entry with label, shortcut key and an id."""

    def __init__(
        self,
        *,
        label: str,
        shortcut: str,
        action_id: str,
        description: str = "",
    ) -> None:
        self.label = label
        self.shortcut = shortcut
        self.action_id = action_id
        self.description = description


# ---------------------------------------------------------------------------
# Menu items
# ---------------------------------------------------------------------------
MENU_ITEMS: list[MenuItem] = [
    MenuItem(label="Run Benchmark", shortcut="R", action_id="run", description="Run a full benchmark sweep"),
    MenuItem(label="View Results", shortcut="V", action_id="results", description="Browse previous benchmark results"),
    MenuItem(label="Configure", shortcut="C", action_id="config", description="Edit configuration settings"),
    MenuItem(label="Help", shortcut="H", action_id="help", description="View documentation and key bindings"),
    MenuItem(label="Quit", shortcut="Q", action_id="quit", description="Exit the application"),
]


# ---------------------------------------------------------------------------
# Main Menu Screen
# ---------------------------------------------------------------------------
class MainMenuScreen(Screen[None]):
    """Application main menu with keyboard-driven navigation.

    The screen emits ``None`` on dismiss.  Children handle their own
    transitions by calling ``self.app.push_screen(...)``.
    """

    DEFAULT_CSS = """
    MainMenuScreen {
        align: center middle;
        background: $surface;
    }

    /* ---- Centered menu box ---- */
    #menu-box {
        width: 44;
        padding: 1 2;
        border: thick $accent;
        background: $panel;
    }

    #title {
        text-style: bold;
        content-align: center top;
        width: 100%;
        margin-bottom: 1;
        padding: 0 1;
    }

    #subtitle {
        content-align: center top;
        width: 100%;
        margin-bottom: 1;
    }

    /* ---- Menu items container ---- */
    #menu-items {
        height: auto;
        margin: 1 0;
    }

    .menu-item-row {
        height: 3;
        width: 100%;
        align: left middle;
        padding: 0 2;
    }

    .menu-item-row.selected {
        background: $accent 30%;
    }

    .menu-item-row.selected > .menu-shortcut {
        text-style: bold;
        color: $accent;
    }

    .menu-item-row.selected > .menu-label {
        text-style: bold;
    }

    .menu-shortcut {
        width: 4;
        text-align: right;
        padding-right: 1;
        color: $text-disabled;
    }

    .menu-label {
        width: 20;
    }

    .menu-desc {
        width: 1fr;
        color: $text-disabled;
        text-align: right;
    }

    /* ---- Actions row ---- */
    #actions-row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    """

    # Track the currently highlighted item index
    _highlighted: int = 0

    BINDINGS: list[Binding] = [
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "select", "Select", show=False),
        Binding("r", "action_run", "Run", show=False),
        Binding("v", "action_results", "Results", show=False),
        Binding("c", "action_config", "Config", show=False),
        Binding("h", "action_help", "Help", show=False),
        Binding("q", "action_quit", "Quit", show=False),
    ]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Vertical(id="menu-box"):
            yield Label("Social Stress Benchmark", id="title")
            yield Label("Evaluate LLM behavior under social pressure", id="subtitle")

            with Vertical(id="menu-items"):
                for idx, item in enumerate(MENU_ITEMS):
                    selected_class = "menu-item-row selected" if idx == 0 else "menu-item-row"
                    with Horizontal(classes=selected_class, id=f"menu-row-{idx}"):
                        yield Label(f"[{item.shortcut}]", classes="menu-shortcut")
                        yield Label(item.label, classes="menu-label")
                        yield Label(item.description, classes="menu-desc")

            # Footer hint
            yield Static("↑↓ Navigate  ·  Enter Select  ·  Q Quit", id="hint")

    def on_mount(self) -> None:
        """Initial focus."""
        self._highlighted = 0
        self._update_selection()

    # ------------------------------------------------------------------
    # Selection rendering
    # ------------------------------------------------------------------
    def _update_selection(self) -> None:
        """Apply/remove the ``selected`` class on menu rows."""
        for idx in range(len(MENU_ITEMS)):
            row = self.query_one(f"#menu-row-{idx}", Horizontal)
            row.set_class(idx == self._highlighted, "selected")

    # ------------------------------------------------------------------
    # Key bindings
    # ------------------------------------------------------------------
    def action_cursor_up(self) -> None:
        """Move highlight up (wrapping)."""
        self._highlighted = (self._highlighted - 1) % len(MENU_ITEMS)
        self._update_selection()
        self._scroll_into_view()

    def action_cursor_down(self) -> None:
        """Move highlight down (wrapping)."""
        self._highlighted = (self._highlighted + 1) % len(MENU_ITEMS)
        self._update_selection()
        self._scroll_into_view()

    def _scroll_into_view(self) -> None:
        """Ensure the currently highlighted row is visible."""
        row = self.query_one(f"#menu-row-{self._highlighted}", Horizontal)
        row.scroll_visible()

    def action_select(self) -> None:
        """Activate the currently highlighted menu item."""
        item = MENU_ITEMS[self._highlighted]
        self._dispatch_action(item.action_id)

    # ------------------------------------------------------------------
    # Action dispatch
    # ------------------------------------------------------------------
    def action_action_run(self) -> None:
        self._dispatch_action("run")

    def action_action_results(self) -> None:
        self._dispatch_action("results")

    def action_action_config(self) -> None:
        self._dispatch_action("config")

    def action_action_help(self) -> None:
        self._dispatch_action("help")

    def action_action_quit(self) -> None:
        self._dispatch_action("quit")

    def _dispatch_action(self, action_id: str) -> None:
        """Route a menu action to the appropriate handler.

        Subclasses or the parent ``App`` can override individual handlers
        to implement the actual screen transitions.
        """
        handler_map = {
            "run": self._on_run,
            "results": self._on_results,
            "config": self._on_config,
            "help": self._on_help,
            "quit": self._on_quit,
        }
        handler = handler_map.get(action_id)
        if handler:
            handler()

    # ------------------------------------------------------------------
    # Handlers — push actual screens via lazy imports
    # ------------------------------------------------------------------
    def _on_run(self) -> None:
        """Open the run configuration screen."""
        from benchmark.tui.screens.run_config import RunConfigScreen
        self.app.push_screen(RunConfigScreen())

    def _on_results(self) -> None:
        """Open the results viewer screen."""
        from benchmark.tui.screens.results import ResultsScreen
        self.app.push_screen(ResultsScreen())

    def _on_config(self) -> None:
        """Open configuration screen."""
        self.notify("Configuration editing coming soon", severity="information")

    def _on_help(self) -> None:
        """Show help."""
        self.notify(
            "↑↓ Navigate · Enter Select · Esc Back · Ctrl+C Quit\n"
            "Configure run parameters → Run Benchmark to start",
            severity="information",
            timeout=8,
        )

    def _on_quit(self) -> None:
        """Exit the application."""
        self.app.exit()


# Make the import pattern work: from benchmark.tui.screens.main_menu import MainMenuScreen
__all__ = ["MainMenuScreen"]
