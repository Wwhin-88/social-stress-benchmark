"""First-run configuration wizard — appears when no config.yaml exists.

Provides a three-step guided setup:
1. Choose reviewer LLM (provider + model + API key/base URL).
2. Add one or more test models.
3. Review and save config.yaml + .env.

Provider is a free-text input — supports any litellm-compatible provider.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_DOTENV_PATH = Path(".env")

API_BASE_PLACEHOLDERS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "local": "http://localhost:11434",
}


# ---------------------------------------------------------------------------
# Helper: build model input fields
# ---------------------------------------------------------------------------
def _model_fields(
    prefix: str,
    provider_default: str = "openai",
    model_placeholder: str = "e.g. gpt-4o",
    api_key_placeholder: str = "sk-…",
) -> list:
    """Return a list of widgets for a model input group (provider, name, key, base URL)."""
    base_placeholder = API_BASE_PLACEHOLDERS.get(provider_default, "(optional)")
    return [
        Label("Provider"),
        Input(
            id=f"{prefix}_provider",
            placeholder="openai / deepseek / openrouter / local / …",
            value=provider_default,
        ),
        Label("Model name"),
        Input(
            id=f"{prefix}_model",
            placeholder=model_placeholder,
        ),
        Label("API key"),
        Input(
            id=f"{prefix}_api_key",
            placeholder=api_key_placeholder,
            password=True,
        ),
        Label("API base URL"),
        Input(
            id=f"{prefix}_api_base",
            placeholder=base_placeholder,
        ),
    ]


# ---------------------------------------------------------------------------
# Welcome / Config Wizard Screen
# ---------------------------------------------------------------------------
class WelcomeScreen(Screen[None]):
    """First-run configuration wizard.

    Emits ``None`` on dismiss.  The parent app is responsible for checking
    whether ``config.yaml`` now exists and switching to the chat screen.
    """

    DEFAULT_CSS = """
    WelcomeScreen {
        align: center middle;
        background: $surface;
    }

    /* ---- Main wizard box ---- */
    #wizard-box {
        width: 56;
        padding: 1 2;
        border: thick $accent;
        background: $panel;
    }

    #wizard-box > #title {
        text-style: bold;
        content-align: center top;
        width: 100%;
        margin-bottom: 1;
    }

    /* ---- Step headers ---- */
    .step-header {
        text-style: bold;
        color: $accent;
        margin-top: 1;
        margin-bottom: 0;
    }

    /* ---- Model field groups ---- */
    .model-fields {
        margin-top: 1;
        margin-bottom: 1;
    }

    .model-fields > Label {
        margin-top: 1;
        margin-bottom: 0;
    }

    .model-fields > Input {
        width: 100%;
    }

    /* ---- Lists of added models (step 2 summary) ---- */
    #added-models-list {
        margin: 1 0;
        height: auto;
        max-height: 8;
        overflow-y: auto;
        border: solid $border;
        padding: 0 1;
    }

    #added-models-list > Static {
        padding: 0 0;
    }

    /* ---- Buttons ---- */
    .button-row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    .button-row > Button {
        min-width: 16;
    }

    /* ---- Summary table in step 3 ---- */
    #summary-container {
        margin: 1 0;
        height: auto;
        border: solid $border;
        padding: 0 1;
    }

    #summary-container > Static {
        padding: 0 0;
    }

    /* ---- Error label ---- */
    #error-label {
        color: $error;
        text-style: bold;
        margin-top: 1;
        text-align: center;
        width: 100%;
    }

    /* Hide sections by default */
    #step2-section, #step3-section {
        display: none;
    }
    """

    # ------------------------------------------------------------------
    # Keybindings
    # ------------------------------------------------------------------

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
    ]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Vertical(id="wizard-box"):
            yield Static("⚙  Social Stress Benchmark  ⚙", id="title")

            # Step 1 ----------------------------------------------------
            yield Static("Step 1 / 3 — Choose Reviewer Model", classes="step-header")
            with Vertical(id="step1-section"):
                yield from _model_fields(
                    prefix="reviewer",
                    model_placeholder="e.g. gpt-4o",
                    api_key_placeholder="REVIEWER API key",
                )
                with Horizontal(classes="button-row"):
                    yield Button("Next: Test Models", id="step1-next", variant="primary")

            # Step 2 ----------------------------------------------------
            yield Static("Step 2 / 3 — Add Test Models", classes="step-header")
            with Vertical(id="step2-section"):
                yield Static(
                    "Test models are the models being evaluated. Add at least one.",
                    id="step2-hint",
                )
                yield Static("", id="added-models-list")
                with Vertical(id="step2-fields"):
                    yield from _model_fields(
                        prefix="test_0",
                        model_placeholder="e.g. gpt-4o-mini",
                        api_key_placeholder="TEST model API key",
                    )
                with Horizontal(classes="button-row"):
                    yield Button("Add Another Model", id="add-another", variant="default")
                    yield Button("Next: Save", id="step2-next", variant="primary")

            # Step 3 ----------------------------------------------------
            yield Static("Step 3 / 3 — Review & Save", classes="step-header")
            with Vertical(id="step3-section"):
                yield Static("Review your configuration below:", id="step3-hint")
                yield Static("", id="summary-container")
                with Horizontal(classes="button-row"):
                    yield Button("← Back", id="step3-back", variant="default")
                    yield Button("Save Configuration", id="save-config", variant="primary")

            # Error display
            yield Static("", id="error-label")

    def on_mount(self) -> None:
        """Focus the first input and set initial field visibility."""
        self._toggle_provider("reviewer")
        self._toggle_provider("test_0")
        self.query_one("#reviewer_provider", Input).focus()

    def _toggle_provider(self, prefix: str) -> None:
        """Show/hide API key fields based on the provider value for a prefix."""
        try:
            prov = self.query_one(f"#{prefix}_provider", Input)
            is_local = prov.value.strip().lower() == "local"
            for field_id in (f"{prefix}_api_key_label", f"{prefix}_api_key"):
                try:
                    self.query_one(f"#{field_id}").display = not is_local
                except Exception:
                    pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def action_go_back(self) -> None:
        """Escape — dismiss this screen."""
        self.dismiss(None)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    @property
    def _test_models(self) -> list[dict[str, str]]:
        return self.__dict__.setdefault("_test_models_list", [])

    @_test_models.setter
    def _test_models(self, value: list[dict[str, str]]) -> None:
        self.__dict__["_test_models_list"] = value

    @property
    def _test_index(self) -> int:
        return self.__dict__.setdefault("_test_index", 0)

    @_test_index.setter
    def _test_index(self, value: int) -> None:
        self.__dict__["_test_index"] = value

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------
    def _show_step(self, step: int) -> None:
        """Show only the given step section."""
        for i in (1, 2, 3):
            section = self.query_one(f"#step{i}-section", Vertical)
            section.display = i == step
        self.query_one("#error-label", Static).update("")

    def _get_field_value(self, prefix: str, field: str) -> str:
        """Return the current value of a model field."""
        widget = self.query_one(f"#{prefix}_{field}")
        return widget.value.strip()

    def _read_model(self, prefix: str) -> dict[str, str] | None:
        """Read provider / model / api_key / api_base for a given prefix."""
        provider = self._get_field_value(prefix, "provider")
        model = self._get_field_value(prefix, "model")
        api_key = self._get_field_value(prefix, "api_key")
        api_base = self._get_field_value(prefix, "api_base")
        is_local = provider.lower() == "local"

        errors: list[str] = []
        if not provider:
            errors.append("Provider is required.")
        if not model:
            errors.append("Model name is required.")
        if not is_local and not api_key:
            errors.append("API key is required.")

        result: dict[str, str] = {"provider": provider, "model": model}

        if is_local:
            result["api_key"] = "not-needed"
        else:
            result["api_key"] = api_key

        if api_base:
            result["api_base"] = api_base
        elif provider.lower() in API_BASE_PLACEHOLDERS:
            errors.append("API base URL is required.")

        if errors:
            self.query_one("#error-label", Static).update("  ".join(errors))
            return None

        return result

    # ------------------------------------------------------------------
    # Provider-dependent field toggling
    # ------------------------------------------------------------------

    @on(Input.Changed)
    def _on_provider_changed(self, event: Input.Changed) -> None:
        """When provider text changes, hide API key field for local models."""
        wid = event.input.id
        if wid and wid.endswith("_provider"):
            prefix = wid.rsplit("_provider", 1)[0]
            is_local = event.value.strip().lower() == "local"
            for field_id in (f"{prefix}_api_key_label", f"{prefix}_api_key"):
                try:
                    self.query_one(f"#{field_id}").display = not is_local
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Handlers — Step 1
    # ------------------------------------------------------------------
    @on(Button.Pressed, "#step1-next")
    def _on_step1_next(self) -> None:
        """Validate reviewer config and advance to step 2."""
        reviewer = self._read_model("reviewer")
        if reviewer is None:
            return
        self._reviewer = reviewer
        self._show_step(2)
        self._rebuild_added_models_list()
        self.query_one("#test_0_provider", Input).focus()

    # ------------------------------------------------------------------
    # Handlers — Step 2
    # ------------------------------------------------------------------
    @on(Button.Pressed, "#add-another")
    def _on_add_another(self) -> None:
        """Commit the current test model and show fresh fields."""
        model = self._read_model(f"test_{self._test_index}")
        if model is None:
            return
        self._test_models = self._test_models + [model]
        self._test_index += 1
        self._rebuild_step2_fields()
        self._rebuild_added_models_list()
        self.query_one(f"#test_{self._test_index}_provider", Input).focus()

    @on(Button.Pressed, "#step2-next")
    def _on_step2_next(self) -> None:
        """Commit the current test model (if any fields filled) and advance to step 3."""
        current = self._read_model(f"test_{self._test_index}")
        if current is not None:
            if current.get("provider") or current.get("model") or current.get("api_key"):
                self._test_models = self._test_models + [current]

        if not self._test_models:
            self.query_one("#error-label", Static).update(
                "Add at least one test model before proceeding."
            )
            return

        self._build_summary()
        self._show_step(3)

    def _rebuild_added_models_list(self) -> None:
        """Refresh the list of already-committed test models."""
        container = self.query_one("#added-models-list", Static)
        if not self._test_models:
            container.update("[dim]No models added yet.[/dim]")
            return

        lines = [f"[bold]Added models ({len(self._test_models)}):[/bold]"]
        for i, m in enumerate(self._test_models, 1):
            prov = m.get("provider", "?")
            mod = m.get("model", "?")
            has_key = bool(m.get("api_key") and m["api_key"] != "not-needed")
            has_base = bool(m.get("api_base"))
            extras = []
            if has_key:
                extras.append("key set")
            if has_base:
                extras.append(f"base={m['api_base']}")
            extra_str = f" ({', '.join(extras)})" if extras else ""
            lines.append(f"  {i}. {prov} / {mod}{extra_str}")
        container.update("\n".join(lines))

    def _rebuild_step2_fields(self) -> None:
        """Replace the step-2 input fields with a fresh set using an incremented prefix."""
        fields_container = self.query_one("#step2-fields", Vertical)
        fields_container.remove_children()
        pfx = f"test_{self._test_index}"
        for widget in _model_fields(
            prefix=pfx,
            model_placeholder="e.g. gpt-4o-mini",
            api_key_placeholder="TEST model API key",
        ):
            fields_container.mount(widget)
        self._toggle_provider(pfx)

    # ------------------------------------------------------------------
    # Handlers — Step 3
    # ------------------------------------------------------------------
    @on(Button.Pressed, "#step3-back")
    def _on_step3_back(self) -> None:
        self._show_step(2)
        self.query_one("#error-label", Static).update("")

    @on(Button.Pressed, "#save-config")
    def _on_save_config(self) -> None:
        """Write config.yaml and .env, then dismiss the screen."""
        self.query_one("#error-label", Static).update("")

        if not self._test_models:
            self.query_one("#error-label", Static).update("No test models configured.")
            return

        # ---- Write .env ----
        env_vars: dict[str, str] = {}
        r = self._reviewer

        if r.get("provider", "").lower() != "local":
            if r.get("api_key") and r["api_key"] != "not-needed":
                env_vars["REVIEWER_API_KEY"] = r["api_key"]

        model_env_idx = 0
        for m in self._test_models:
            if m.get("provider", "").lower() == "local":
                continue
            if m.get("api_key") and m["api_key"] != "not-needed":
                model_env_idx += 1
                env_vars[f"MODEL_{model_env_idx}_API_KEY"] = m["api_key"]

        env_path = DEFAULT_DOTENV_PATH
        existing_env = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        with open(env_path, "a", encoding="utf-8") as f:
            for var_name, var_value in env_vars.items():
                if f"{var_name}=" not in existing_env:
                    f.write(f"{var_name}={var_value}\n")

        # ---- Write config.yaml ----
        r_prov = r.get("provider", "")
        reviewer_model: dict[str, str] = {"provider": r_prov, "model": r.get("model", "")}
        if r_prov.lower() == "local":
            reviewer_model["api_key"] = "not-needed"
        else:
            reviewer_model["api_key"] = "${REVIEWER_API_KEY}"
        if r.get("api_base"):
            reviewer_model["api_base"] = r["api_base"]

        test_models_yaml = []
        tm_env_idx = 0
        for m in self._test_models:
            entry: dict[str, str] = {"provider": m["provider"], "model": m["model"]}
            prov = m.get("provider", "").lower()
            if prov == "local":
                entry["api_key"] = "not-needed"
            else:
                tm_env_idx += 1
                entry["api_key"] = f"${{MODEL_{tm_env_idx}_API_KEY}}"
            if m.get("api_base"):
                entry["api_base"] = m["api_base"]
            test_models_yaml.append(entry)

        config_data = {
            "reviewer": reviewer_model,
            "models_to_test": test_models_yaml,
            "scenarios": [],
            "defender_variants": ["weak", "normal", "aggressive"],
            "output": {"dir": "./results", "format": "json", "auto_save": True},
        }

        with open(DEFAULT_CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

        self.dismiss()

    # ------------------------------------------------------------------
    # Summary builder
    # ------------------------------------------------------------------
    def _build_summary(self) -> None:
        lines: list[str] = []
        lines.append("[bold underline]Reviewer[/bold underline]")
        lines.append(f"  Provider: {self._reviewer.get('provider', '?')}")
        lines.append(f"  Model:    {self._reviewer.get('model', '?')}")
        if self._reviewer.get("api_base"):
            lines.append(f"  Base URL: {self._reviewer['api_base']}")

        lines.append("")
        lines.append(f"[bold underline]Test Models ({len(self._test_models)})[/bold underline]")
        for i, m in enumerate(self._test_models, 1):
            extra = f" (base={m['api_base']})" if m.get("api_base") else ""
            lines.append(f"  {i}. {m.get('provider', '?')} / {m.get('model', '?')}{extra}")

        lines.append("")
        lines.append("[bold underline]Output[/bold underline]")
        lines.append("  Directory: ./results")
        lines.append("  Format:    json")
        lines.append("")
        lines.append("[dim]API keys will be stored in .env[/dim]")

        self.query_one("#summary-container", Static).update("\n".join(lines))
