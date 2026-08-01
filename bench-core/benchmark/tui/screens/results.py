"""Results viewer screen — list and inspect previous benchmark runs.

Scans the ``results/`` directory for run folders (``run_<id>/``) and
displays a DataTable with run_id, model(s), scenario, and composite score.
Select a row to see a summary; press Enter to view raw JSON details.
"""

from __future__ import annotations

import json
from pathlib import Path

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label, Static
from textual.binding import Binding

def _resolve_results_dir() -> Path:
    """Resolve the results directory relative to the project root."""
    this_file = Path(__file__).resolve()
    root = this_file.parent.parent.parent.parent
    if (root / "config.yaml").exists() or (root / "config.example.yaml").exists():
        return root / "results"
    return Path.cwd() / "results"


RESULTS_DIR: Path = _resolve_results_dir()


def _load_run_metadata(run_dir: Path) -> list[dict]:
    """Extract run metadata from a single run directory.

    Each run directory contains model subdirectories with individual
    ``.json`` result files and/or a ``report.json`` at the top level.

    Returns a list of dicts with keys: run_id, model, scenario, defender,
    timestamp, composite_score.
    """
    run_id = run_dir.name.removeprefix("run_")
    results: list[dict] = []

    # 1. Try the top-level report.json (comprehensive)
    report_path = run_dir / "report.json"
    if report_path.exists():
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
            for entry in data.get("runs", []):
                results.append({
                    "run_id": entry.get("run_id", run_id),
                    "model": entry.get("model", "?"),
                    "scenario": entry.get("scenario", "?"),
                    "defender": entry.get("defender", "?"),
                    "timestamp": entry.get("timestamp", "?"),
                    "composite_score": entry.get("composite_score", 0.0),
                })
            if results:
                return results
        except (json.JSONDecodeError, KeyError):
            pass

    # 2. Scan model subdirectories
    for model_dir in sorted(run_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        model_name = model_dir.name

        # 2a. Summary JSON per model
        summary_path = model_dir / "summary.json"
        if summary_path.exists():
            try:
                data = json.loads(summary_path.read_text(encoding="utf-8"))
                defenders = data.get("defenders", {})
                for defender_name, defender_data in defenders.items():
                    results.append({
                        "run_id": data.get("run_id", run_id),
                        "model": data.get("model", model_name),
                        "scenario": data.get("scenario", "?"),
                        "defender": defender_name,
                        "timestamp": defender_data.get("timestamp", "?"),
                        "composite_score": defender_data.get("composite_score", 0.0),
                    })
                continue
            except (json.JSONDecodeError, KeyError):
                pass

        # 2b. Individual .json files (skip summary.json itself)
        for result_file in sorted(model_dir.glob("*.json")):
            if result_file.name == "summary.json":
                continue
            try:
                data = json.loads(result_file.read_text(encoding="utf-8"))
                results.append({
                    "run_id": data.get("run_id", run_id),
                    "model": data.get("model", model_name),
                    "scenario": data.get("scenario", "?"),
                    "defender": data.get("defender", "?"),
                    "timestamp": data.get("timestamp", "?"),
                    "composite_score": data.get("composite_score", 0.0),
                })
            except (json.JSONDecodeError, KeyError):
                continue

    return results


def _load_raw_result(run_dir: Path, model: str, defender: str) -> dict | None:
    """Load the raw JSON of a single defender result."""
    for path in [
        run_dir / model / f"{defender}.json",
        run_dir / model / "summary.json",
    ]:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, FileNotFoundError):
                pass
    return None


# ── CopyOnSelectStatic: Static that auto-copies selected text on mouse-up ──

class CopyOnSelectStatic(Static):
    """Static widget that auto-copies selected text on mouse release after drag.

    On macOS, simulates Cmd+C via osascript to copy terminal-selected text.
    The 50 ms timer delay ensures the terminal processes the mouse release
    before the copy keystroke is dispatched.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mouse_down_pos: tuple[int, int] | None = None

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._mouse_down_pos = (event.x, event.y)

    def on_click(self, event: events.Click) -> None:
        if self._mouse_down_pos is not None:
            dx = abs(event.x - self._mouse_down_pos[0])
            dy = abs(event.y - self._mouse_down_pos[1])
            if dx > 3 or dy > 3:
                self.set_timer(0.05, self._copy_selection)
            self._mouse_down_pos = None

    @staticmethod
    def _copy_selection() -> None:
        import subprocess
        import sys
        try:
            if sys.platform == "darwin":
                subprocess.run(
                    ["osascript", "-e",
                     'tell application "System Events" to keystroke "c" using command down'],
                    check=False, timeout=1,
                )
        except Exception:
            pass



class ResultsScreen(Screen):
    """Display and inspect previous benchmark runs."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back to menu", show=True),
        Binding("up", "cursor_up", "Move up", show=False),
        Binding("down", "cursor_down", "Move down", show=False),
        Binding("enter", "view_details", "View details", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._runs: list[dict] = []
        self._selected_index: int = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="results-screen"):
            yield Label("Previous Benchmark Runs", id="results-header")
            yield DataTable(id="results-table")
            yield CopyOnSelectStatic("", id="results-summary")
        yield Footer()

    def on_mount(self) -> None:
        """Scan results directory and populate the DataTable."""
        table = self.query_one("#results-table", DataTable)
        table.cursor_type = "row"

        results_dir = RESULTS_DIR
        if not results_dir.exists():
            table.show_cursor = False
            self.query_one("#results-header", Label).update(
                "No results found — run a benchmark first!"
            )
            return

        run_dirs = sorted(results_dir.glob("run_*"), reverse=True)
        if not run_dirs:
            table.show_cursor = False
            self.query_one("#results-header", Label).update(
                "No results found — run a benchmark first!"
            )
            return

        # Clear and set up columns
        table.clear(columns=True)
        table.add_columns("Run ID", "Model(s)", "Scenario", "Score", "Runs")

        for run_dir in run_dirs:
            metadata_list = _load_run_metadata(run_dir)
            if not metadata_list:
                continue

            run_id = metadata_list[0]["run_id"]
            # Summarize by run: collect unique models + avg score
            models = sorted({m["model"] for m in metadata_list})
            scenarios = sorted({m["scenario"] for m in metadata_list})
            scores = [m["composite_score"] for m in metadata_list]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            model_label = ", ".join(models) if len(models) <= 3 else f"{len(models)} models"
            scenario_label = ", ".join(scenarios) if len(scenarios) <= 2 else f"{len(scenarios)} scenarios"

            table.add_row(
                run_id,
                model_label,
                scenario_label,
                f"{avg_score:.1f}",
                str(len(metadata_list)),
            )
            # Store metadata for detail lookup
            self._runs.append({
                "run_id": run_id,
                "models": models,
                "scenarios": scenarios,
                "metadata_list": metadata_list,
            })

        if not self._runs:
            table.show_cursor = False
            self.query_one("#results-header", Label).update(
                "No results found — run a benchmark first!"
            )

    # ------------------------------------------------------------------
    # Navigate
    # ------------------------------------------------------------------

    def action_cursor_up(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.action_cursor_up()

    def action_cursor_down(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.action_cursor_down()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    @on(DataTable.RowSelected)
    @on(DataTable.RowHighlighted)
    def _on_row_selected(self, event: DataTable.RowSelected | DataTable.RowHighlighted) -> None:
        """Show summary for the highlighted/selected row."""
        if event.row_key.value is None:
            return
        self._update_detail(event.row_key)
        """Show summary for the highlighted/selected row."""
        self._update_detail(event.row_key)

    def _update_detail(self, row_key) -> None:
        """Update the summary area with details for the given row."""
        summary = self.query_one("#results-summary", Static)
        table = self.query_one("#results-table", DataTable)

        try:
            row_index = table.get_row_index(row_key)
        except (KeyError, IndexError):
            row_index = table.rows[row_key]
        except (KeyError, IndexError):
            summary.update("")
            return

        if row_index < 0 or row_index >= len(self._runs):
            summary.update("")
            return

        run_info = self._runs[row_index]
        metadata = run_info.get("metadata_list", [])

        lines = [f"[bold]Run:[/bold] {run_info['run_id']}"]
        defender_scores = []
        for m in metadata:
            ds = m.get("composite_score", 0)
            defender_scores.append(ds)
            lines.append(
                f"  {m['model']} / {m['scenario']} / {m['defender']}: "
                f"[bold]{ds:.1f}[/bold]"
            )
        if defender_scores:
            avg = sum(defender_scores) / len(defender_scores)
            lines.append(f"[bold]Average Score:[/bold] {avg:.1f}")

        summary.update("\n".join(lines))

    def action_view_details(self) -> None:
        """Open detailed view of the currently selected run.

        Attempts to show raw JSON content of the first result file.
        """
        table = self.query_one("#results-table", DataTable)
        cursor = table.cursor_coordinate
        if cursor is None or cursor.row >= len(self._runs):
            return

        run_info = self._runs[cursor.row]
        run_dir = RESULTS_DIR / f"run_{run_info['run_id']}"

        # Load the raw report.json if it exists, otherwise show first result
        raw: dict | None = None
        report_path = run_dir / "report.json"
        if report_path.exists():
            try:
                raw = json.loads(report_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, FileNotFoundError):
                pass

        if raw is None:
            metadata = run_info.get("metadata_list", [])
            if metadata:
                first = metadata[0]
                raw = _load_raw_result(run_dir, first["model"], first["defender"])

        if raw is None:
            summary = self.query_one("#results-summary", Static)
            summary.update("[warning]No detailed data available[/warning]")
            return

        # Show raw JSON in the summary area
        summary = self.query_one("#results-summary", Static)
        pretty = json.dumps(raw, indent=2, ensure_ascii=False)
        # Truncate very long output
        if len(pretty) > 5000:
            pretty = pretty[:5000] + "\n... (truncated)"
        summary.update(f"[bold]Raw Data[/bold]\n{pretty}")
