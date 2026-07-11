"""Benchmark engine — iterates models × scenarios × defenders."""

from __future__ import annotations

import logging
import signal
import sys
from pathlib import Path

from benchmark.api import SkipModel, LLMError
from benchmark.config import Config
from benchmark.models import RunResult
from benchmark.runner import run_scenario
from benchmark.storage import get_run_id, load_partial_results, save_model_summary
from benchmark.reporter import print_run_result, print_header

logger = logging.getLogger(__name__)


class BenchmarkEngine:
    """Orchestrates the full benchmark run.

    Iterates: models_to_test × scenarios × defender_variants
    Supports: KeyboardInterrupt save, resume from partial results.
    """

    def __init__(self, config: Config):
        self.config = config
        self.results: list[RunResult] = []
        self._abort = False
        self.run_id = get_run_id()

        # Register signal handler for graceful Ctrl+C
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, sig, frame):
        """Handle Ctrl+C gracefully — save partial results."""
        print("\n\n⚠️  Benchmark interrupted. Saving partial results...")
        self._abort = True

    def run(self) -> list[RunResult]:
        """Execute the full benchmark."""
        print_header(f"Social Stress Benchmark — Run {self.run_id}")

        model_count = len(self.config.models_to_test)
        scenario_count = len(self.config.scenarios)
        defender_count = len(self.config.defender_variants)
        total = model_count * scenario_count * defender_count
        completed = 0

        logger.info(
            "Starting benchmark: %d models × %d scenarios × %d defenders = %d runs",
            model_count, scenario_count, defender_count, total,
        )

        for model_cfg in self.config.models_to_test:
            if self._abort:
                break

            model_label = f"{model_cfg.provider}/{model_cfg.model}"
            print_header(f"Testing Model: {model_label}")

            for scenario_name in self.config.scenarios:
                if self._abort:
                    break

                # Load scenario
                from scenarios import load_scenario
                try:
                    scenario = load_scenario(scenario_name)
                except Exception as e:
                    logger.error("Failed to load scenario '%s': %s", scenario_name, e)
                    continue

                print_header(f"Scenario: {scenario.name}")

                # Try to resume partial results
                partial = load_partial_results(self.config.output.dir, self.run_id, model_cfg.model)
                completed_defenders = set(partial.keys())

                for defender in self.config.defender_variants:
                    if self._abort:
                        break

                    # Skip if already completed
                    if defender in completed_defenders:
                        logger.info("Skipping %s/%s/%s — already completed", model_cfg.model, scenario_name, defender)
                        result = partial[defender]
                        self.results.append(result)
                        print_run_result(result)
                        completed += 1
                        continue

                    try:
                        result = run_scenario(
                            model_config=model_cfg,
                            reviewer_config=self.config.reviewer,
                            scenario=scenario,
                            defender_variant=defender,
                            output_dir=self.config.output.dir,
                            run_id=self.run_id,
                        )
                    except SkipModel as e:
                        logger.error("Skipping model %s: %s", model_label, e)
                        break  # Skip remaining defenders for this model
                    except LLMError as e:
                        logger.error("Skipping defender %s for %s: %s", defender, model_label, e)
                        continue
                    except Exception as e:
                        logger.error(
                            "Unexpected error for %s/%s/%s: %s",
                            model_label, scenario_name, defender, e,
                        )
                        continue

                    self.results.append(result)
                    print_run_result(result)
                    completed += 1

                    # Print progress
                    print(f"  Progress: {completed}/{total} runs completed")

                # Save model summary after all defenders
                model_results = [r for r in self.results if r.model == model_cfg.model]
                if len(model_results) >= 1 and self.config.output.auto_save:
                    save_model_summary(model_results, self.config.output.dir, model_cfg.model)

        return self.results
