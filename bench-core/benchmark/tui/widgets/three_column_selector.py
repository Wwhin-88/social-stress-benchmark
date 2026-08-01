"""Three-column grid selector with mutual exclusion and dynamic resizing.

Column 1: Profiles (single-select radio)
Column 2: Scenarios (multi-select)
Column 3: Sub-tests (multi-select)

Rules:
- Selecting a profile disables scenarios + sub-tests columns.
- Selecting a scenario or sub-test disables the profiles column.
- Only one profile can be selected at a time.
- Focus moves left/right with arrow keys; up/down within the active column.
- Tab enters the selector, Shift+Enter confirms all selections.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget

from benchmark.tui.widgets.column_view import ColumnView


class ThreeColumnSelector(Widget):
    """Three-column layout for profile / scenario / sub-test selection.

    Args:
        profiles: List of profile names (e.g. ``["quick", "full", "regression"]``).
        scenarios: List of scenario IDs.
        subtests: List of sub-test IDs for the currently selected scenario(s).
    """

    DEFAULT_CSS = """
    ThreeColumnSelector {
        height: 100%;
        width: 100%;
    }
    ThreeColumnSelector Grid {
        height: 100%;
        grid-size: 3;
        grid-columns: 1fr 1fr 1fr;
        grid-gutter: 1 1;
    }
    ThreeColumnSelector Grid.active-left {
        grid-columns: 2fr 1fr 1fr;
    }
    ThreeColumnSelector Grid.active-center {
        grid-columns: 1fr 2fr 1fr;
    }
    ThreeColumnSelector Grid.active-right {
        grid-columns: 1fr 1fr 2fr;
    }
    """

    BINDINGS = [
        Binding("left", "focus_left", "Move left", show=False),
        Binding("right", "focus_right", "Move right", show=False),
        Binding("shift+enter", "confirm_selection", "Confirm all", show=False),
    ]

    class SelectionChanged(Message, bubble=True):
        """Emitted whenever selection state changes."""

    class Confirmed(Message, bubble=True):
        """Emitted when Shift+Enter confirms the full selection.

        Attrs:
            selected_profile: Profile name or ``None``.
            selected_scenarios: List of selected scenario IDs.
            selected_subtests: List of selected sub-test IDs.
        """

        def __init__(
            self,
            profile: str | None,
            scenarios: list[str],
            subtests: list[str],
        ) -> None:
            super().__init__()
            self.selected_profile = profile
            self.selected_scenarios = scenarios
            self.selected_subtests = subtests

    active_column: reactive[str] = reactive("left")  # "left" | "center" | "right"

    def __init__(
        self,
        profiles: list[str],
        scenarios: list[str],
        subtests: list[str],
        *,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
    ) -> None:
        super().__init__(name=name, id=id)
        self._profile_items = list(profiles)
        self._scenario_items = list(scenarios)
        self._subtest_items = list(subtests)

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Grid(id="selector-grid"):
            yield ColumnView(
                "Profiles",
                self._profile_items,
                select_mode="single",
                id="col-profiles",
            )
            yield ColumnView(
                "Scenarios",
                self._scenario_items,
                select_mode="multi",
                id="col-scenarios",
            )
            yield ColumnView(
                "Sub-tests",
                self._subtest_items,
                select_mode="multi",
                id="col-subtests",
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        """Set initial focus to the profiles column."""
        self._apply_column_focus()

    # ------------------------------------------------------------------
    # Focus management
    # ------------------------------------------------------------------

    def watch_active_column(self, old: str, new: str) -> None:
        """When active column changes, update focus and CSS class."""
        if not self.is_mounted:
            return
        self._apply_column_focus()
        # Update grid CSS class for dynamic resizing
        grid = self.query_one("#selector-grid", Grid)
        grid.remove_class("active-left", "active-center", "active-right")
        grid.add_class(f"active-{new}")

    def _apply_column_focus(self) -> None:
        """Move focus to the active column."""
        if not self.is_mounted:
            return
        col_id = {
            "left": "#col-profiles",
            "center": "#col-scenarios",
            "right": "#col-subtests",
        }.get(self.active_column, "#col-profiles")

        col = self.query_one(col_id, ColumnView)
        if not col.disabled:
            col.focus()

    def _get_focusable_columns(self) -> list[tuple[str, str]]:
        """Return list of (column_key, widget_id) for non-disabled columns."""
        mapping = [
            ("left", "#col-profiles"),
            ("center", "#col-scenarios"),
            ("right", "#col-subtests"),
        ]
        result: list[tuple[str, str]] = []
        for key, wid in mapping:
            col = self.query_one(wid, ColumnView)
            if not col.disabled:
                result.append((key, wid))
        return result

    # ------------------------------------------------------------------
    # Actions (key bindings)
    # ------------------------------------------------------------------

    def action_focus_left(self) -> None:
        """Move focus to the previous non-disabled column."""
        focusable = self._get_focusable_columns()
        if not focusable:
            return
        keys = [k for k, _ in focusable]
        try:
            idx = keys.index(self.active_column)
            new_idx = (idx - 1) % len(keys)
        except ValueError:
            new_idx = 0
        self.active_column = keys[new_idx]

    def action_focus_right(self) -> None:
        """Move focus to the next non-disabled column."""
        focusable = self._get_focusable_columns()
        if not focusable:
            return
        keys = [k for k, _ in focusable]
        try:
            idx = keys.index(self.active_column)
            new_idx = (idx + 1) % len(keys)
        except ValueError:
            new_idx = 0
        self.active_column = keys[new_idx]

    def action_confirm_selection(self) -> None:
        """Shift+Enter — emit final confirmed selection."""
        profile = self.selected_profile
        scenarios = self.selected_scenarios
        subtests = self.selected_subtests
        self.post_message(self.Confirmed(profile, scenarios, subtests))

    # ------------------------------------------------------------------
    # Selection logic — mutual exclusion
    # ------------------------------------------------------------------

    @on(ColumnView.Selected)
    def _on_column_selected(self, event: ColumnView.Selected) -> None:
        """Handle selection toggle in any column."""
        col_id = event.column_view.id

        if col_id == "col-profiles":
            self._sync_profile_blocking()
        elif col_id in ("col-scenarios", "col-subtests"):
            self._sync_scenario_blocking()

        self.post_message(self.SelectionChanged())

    def _sync_profile_blocking(self) -> None:
        """When profile selection changes, block/unblock scenarios+subtests."""
        profiles_col = self.query_one("#col-profiles", ColumnView)
        scenarios_col = self.query_one("#col-scenarios", ColumnView)
        subtests_col = self.query_one("#col-subtests", ColumnView)

        if profiles_col.has_selection:
            scenarios_col.disabled = True
            subtests_col.disabled = True
            scenarios_col.reset_selection()
            subtests_col.reset_selection()
        else:
            scenarios_col.disabled = False
            subtests_col.disabled = False

        # If active column was blocked, move focus to profiles
        if self.active_column in ("center", "right") and (
            scenarios_col.disabled or subtests_col.disabled
        ):
            self.active_column = "left"

    def _sync_scenario_blocking(self) -> None:
        """When scenario/subtest selection changes, block/unblock profiles."""
        profiles_col = self.query_one("#col-profiles", ColumnView)
        scenarios_col = self.query_one("#col-scenarios", ColumnView)
        subtests_col = self.query_one("#col-subtests", ColumnView)

        any_selected = scenarios_col.has_selection or subtests_col.has_selection

        if any_selected:
            profiles_col.disabled = True
            profiles_col.reset_selection()
        else:
            profiles_col.disabled = False

        if self.active_column == "left" and profiles_col.disabled:
            if not scenarios_col.disabled:
                self.active_column = "center"
            elif not subtests_col.disabled:
                self.active_column = "right"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def selected_profile(self) -> str | None:
        profiles = self.query_one("#col-profiles", ColumnView).selected_items
        return profiles[0] if profiles else None

    @property
    def selected_scenarios(self) -> list[str]:
        return self.query_one("#col-scenarios", ColumnView).selected_items

    @property
    def selected_subtests(self) -> list[str]:
        return self.query_one("#col-subtests", ColumnView).selected_items

    def update_subtests(self, items: list[str]) -> None:
        """Replace sub-test options (e.g. when scenario selection changes)."""
        self.query_one("#col-subtests", ColumnView).set_items(items)

    def get_config(self) -> dict:
        """Return current selection as a dict for run configuration."""
        return {
            "profile": self.selected_profile,
            "scenarios": self.selected_scenarios,
            "subtests": self.selected_subtests,
        }
