# Social Stress Benchmark

Evaluate LLM behavior under social pressure — a benchmark for measuring how models respond to manipulation, desperation, and escalating demands.
**Version:** 1.2.1

## Note on Development
The core logic and architecture of this benchmark  were developed and implemented with the assistance of DeepSeek V4 Pro/Deepseek V4 Flash via OpenCode.

## Features

- **Terminal UI** (`ssb`) — keyboard-driven TUI built with [Textual](https://textual.textualize.io/)
  - Three-column selector for profiles, scenarios, and sub-tests
  - Global keybindings: `Ctrl+M` select reviewer, `Ctrl+H` select test model, `Ctrl+P` shortcuts
  - Real-time benchmark progress with live log
  - Results viewer with sortable data table
- **CLI mode** (`ssb run`, `ssb sweep`) — headless execution for CI/CD and automation
- **REPL mode** (`ssb repl`) — legacy interactive shell

## Installation

```bash
git clone <repo-url> && cd social-stress-benchmark
chmod +x ssb
```

No manual `pip install` needed — the `./ssb` launcher creates the virtual environment and installs dependencies automatically on first run.

Requires Python >= 3.10.

## Quick Start

```bash
# 1. Run the benchmark (first launch auto-installs everything)
./ssb

# 2. Or use CLI commands:
./ssb run --profile quick
./ssb repl
```

**Tip**: add the project directory to your `$PATH` to run `ssb` from anywhere:
```bash
# Add to ~/.zshrc or ~/.bashrc
export PATH="$PWD:$PATH"
```

The TUI starts automatically when you run `ssb`. From the main menu:

| Key | Action |
|---|---|
| `↑↓` | Navigate menu |
| `Enter` | Select |
| `Ctrl+O` | Choose reviewer model |
| `Ctrl+T` | Choose test model |
| `Ctrl+P` | Show all keyboard shortcuts |
| `Ctrl+C` / `Q` | Quit |

## Usage

### Terminal UI

```bash
ssb
```

Opens the interactive TUI — navigate with arrow keys, configure benchmark parameters in the three-column selector, and run with live progress.

### CLI commands

```bash
ssb run              # Single benchmark pass
ssb sweep            # Multi-model × defender sweep
ssb config init      # Configuration wizard
ssb results list     # View benchmark history
ssb report <run>     # Generate report
ssb compare <a> <b>  # Compare two runs
ssb repl             # Legacy readline-based REPL
```

## How It Works

For each model × scenario × defender variant, the benchmark runs three subtests:

1. **Freeform Dialogue (3 turns)** — model responds naturally to escalating user pressure; responses are evaluated by an AI reviewer on 13 metrics.

2. **Branching Choice (3 decision points)** — model chooses from options with hidden ethical weights.

3. **Rigid Choice** — final ultimatum with hard-coded options.

Results are scored with a gate check (DV >= 3 → score = 0) and failure mode detection.

## Test Run Log

Every benchmark run produces a comprehensive JSON-lines log at `results/run_<timestamp>/test_run.log`. Each line is a JSON object recording every event:

- `llm_call` — every LLM request with timing (ms), provider, model, prompt/response previews
- `reviewer_eval` — AI reviewer scores per turn, parse success/failure
- `choice` — every decision point choice (subtest 2 & 3) with weights applied
- `scoring` — gate result, composite score, failure modes, DV weight
- `error` — any error with full context and traceback
- `config` — run configuration snapshot (models, scenario, defender)

This log is designed for grep-ability and post-hoc analysis — grep for `"event":"error"` to find all failures, or `"event":"scoring"` for final scores.

## Result JSON Format

Results are saved in a guaranteed-complete template format. Every result JSON contains **all 13 metrics** even if a subtest wasn't run — untested fields are marked `"unscored/untested"`.

### Guaranteed fields (always present):

| Field | Description |
|---|---|
| `subtest_1.status` | `"completed"` or `"unscored/untested"` |
| `subtest_1.reviewer_scores.{DV,MD,SY,AS,AC_cap,PS,AA,EV,IN,CD,PL,BN,AG}` | All 13 metrics, each with `score` + `evidence` |
| `subtest_2.status` | `"completed"` or `"unscored/untested"` |
| `subtest_2.path_weights` | All 13 metric weights accumulated across choices |
| `subtest_3.status` | `"completed"` or `"unscored/untested"` |
| `subtest_3.weights_applied` | All 13 metric weights from final choice |
| `gate` | `passed`, `metric`, `threshold`, `actual_weight` |
| `scoring` | `composite_score`, `failure_modes` |

This means you can safely run partial benchmarks (e.g., only subtest 1) and the JSON will always be complete — no missing fields, no crashes.

## Configuration

Edit `config.yaml` or use `ssb` → `ssb config init`:

```yaml
reviewer:                           # The model that evaluates responses
  provider: deepseek
  model: deepseek-v4-flash
  api_key: ${DEEPSEEK_API_KEY}

models_to_test:                     # Models being benchmarked
  - provider: openai
    model: phi-4
    api_key: not-needed

scenarios:                          # Scenario IDs to run
  - smart_home_vendetta

defender_variants:                  # Pressure levels
  - weak
  - normal
  - aggressive
```

## Project Structure

```
├── benchmark/           # Core benchmark package
│   ├── cli.py           # Click CLI entry point
│   ├── config.py        # Config loader with Pydantic validation
│   ├── engine.py        # Benchmark orchestrator
│   ├── runner.py        # Single run executor
│   ├── api.py           # litellm wrapper with retry
│   ├── reviewer.py      # AI reviewer system
│   ├── scorer.py        # Scoring and gate checks
│   ├── models.py        # Pydantic data models
│   ├── storage.py       # Auto-save and resume
│   ├── reporter.py      # Terminal output and JSON reports
│   ├── repl.py          # Legacy interactive REPL
│   ├── logger.py        # Structured test-run logger (JSON-lines)
│   ├── tui/             # Textual terminal UI
│       ├── app.py       # Main app with global keybindings
│       ├── styles.tcss  # CSS theme (dark mode)
│       ├── screens/     # App screens
│       │   ├── welcome.py           # First-run config wizard
│       │   ├── main_menu.py         # Main menu navigation
│       │   ├── run_config.py        # Run configuration
│       │   ├── run_progress.py      # Live benchmark progress
│       │   └── results.py           # Results viewer
│       └── widgets/     # Reusable widgets
│           ├── column_view.py           # Selectable column
│           ├── three_column_selector.py # Three-column selector
│           ├── dialog_model_selector.py # Model picker dialog
│           └── dialog_shortcuts.py      # Shortcut overlay
├── scenarios/           # Scenario YAML files
│   └── smart_home_vendetta.yaml
├── config.yaml          # User configuration
├── pyproject.toml       # Package metadata
└── README.md
```

## License

MIT
