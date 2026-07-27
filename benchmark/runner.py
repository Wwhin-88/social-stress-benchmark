"""Scenario runner — runs one scenario with one model + defender variant."""

from __future__ import annotations

import logging
import time
import traceback
from datetime import datetime

from benchmark.api import call_llm, LLMError, SkipModel
from benchmark.config import LLMConfig
from benchmark.logger import TestLogger
from benchmark.models import (
    Scenario,
    Turn,
    Choice,
    Subtest1,
    Subtest2,
    Subtest3,
    RunResult,
    ReviewerScores,
)
from benchmark.reviewer import review_response
from benchmark.scorer import (
    accumulate_weights,
    check_gate,
    compute_composite_score,
    detect_failure_modes,
)
from benchmark.storage import save_run_result, get_run_id

logger = logging.getLogger(__name__)


def run_scenario(
    model_config: LLMConfig,
    reviewer_config: LLMConfig,
    scenario: Scenario,
    defender_variant: str,
    output_dir: str = "./results",
    run_id: str | None = None,
) -> RunResult:
    """Run a single scenario with one model + defender variant.

    Lifecycle:
    1. Subtest 1: Freeform Dialogue (3 turns) + AI reviewer evaluation
    2. Subtest 2: Branching Choice (3 decision points)
    3. Subtest 3: Rigid Choice (final ultimatum)
    4. Gate check + failure mode detection
    5. Composite score calculation
    6. Auto-save
    """
    if run_id is None:
        run_id = get_run_id()

    scenario_id = scenario.id

    logger.info(
        "Running: model=%s scenario=%s defender=%s",
        model_config.model, scenario_id, defender_variant,
    )

    # ── Initialize structured logger ──────────────────────────────────
    tlog = TestLogger(run_id, output_dir)
    tlog.start()
    tlog.log_config(
        reviewer=f"{reviewer_config.provider}/{reviewer_config.model}",
        test_model=f"{model_config.provider}/{model_config.model}",
        scenario=scenario_id,
        defender=defender_variant,
    )

    # Track whether all subtests completed without errors
    all_succeeded = True

    # -------------------------------------------------------------------
    # Subtest 1: Freeform Dialogue (3 turns)
    # -------------------------------------------------------------------
    turns: list[Turn] = []
    defender_context = scenario.defender_variants.get(defender_variant, "")

    for turn_def in scenario.subtests.subtest_1.turns:
        prompt = turn_def.prompt

        # Inject defender variant context into turn 2
        if turn_def.id == 2 and defender_context:
            prompt = prompt + "\n\n" + defender_context

        system_message = {"role": "system", "content": scenario.system_prompt}
        user_message = {"role": "user", "content": prompt}
        messages = [system_message, user_message]

        t0 = time.time()
        try:
            response = call_llm(
                provider=model_config.provider,
                model=model_config.model,
                api_key=model_config.api_key,
                api_base=model_config.api_base or None,
                messages=messages,
                max_tokens=model_config.max_tokens,
                temperature=model_config.temperature,
            )
            latency_ms = (time.time() - t0) * 1000
            tlog.log_llm_call(
                subtest="subtest_1",
                turn=turn_def.id,
                provider=model_config.provider,
                model=model_config.model,
                prompt_preview=prompt,
                response_preview=response,
                latency_ms=latency_ms,
                status="success",
            )
        except SkipModel:
            tlog.finish(status="failed")
            raise
        except LLMError as e:
            latency_ms = (time.time() - t0) * 1000
            all_succeeded = False
            logger.error("Model call failed on turn %d: %s", turn_def.id, e)
            response = f"[ERROR: {e}]"
            tlog.log_llm_call(
                subtest="subtest_1",
                turn=turn_def.id,
                provider=model_config.provider,
                model=model_config.model,
                prompt_preview=prompt,
                response_preview=response,
                latency_ms=latency_ms,
                status="error",
                error=str(e),
            )
            tlog.log_error(
                context=f"subtest_1/turn_{turn_def.id}",
                error_type="LLMError",
                message=str(e),
                traceback=traceback.format_exc(),
            )

        turn_record = Turn(
            id=turn_def.id,
            prompt=prompt,
            response=response,
        )
        turns.append(turn_record)

    # Reviewer evaluation of subtest 1
    reviewer_scores = ReviewerScores()
    for turn in turns:
        t0 = time.time()
        try:
            result = review_response(
                reviewer_config=reviewer_config,
                scenario_id=scenario_id,
                defender_variant=defender_variant,
                turn=turn.id,
                model_response=turn.response,
            )
            latency_ms = (time.time() - t0) * 1000
            # Merge scores (later turns override earlier on same metric)
            for metric in ReviewerScores.model_fields:
                incoming = getattr(result.scores, metric, None)
                if incoming is not None and incoming.score is not None:
                    setattr(reviewer_scores, metric, incoming)
            # Build raw scores dict for logging
            raw_scores = {}
            for metric in ReviewerScores.model_fields:
                ms = getattr(result.scores, metric, None)
                if ms is not None:
                    raw_scores[metric] = ms.score
            tlog.log_reviewer_eval(
                turn=turn.id,
                raw_scores=raw_scores,
                parse_success=True,
                reviewer_provider=reviewer_config.provider,
                reviewer_model=reviewer_config.model,
                latency_ms=latency_ms,
            )
        except SkipModel:
            tlog.finish(status="failed")
            raise
        except Exception as e:
            latency_ms = (time.time() - t0) * 1000
            all_succeeded = False
            logger.error("Review failed for turn %d: %s", turn.id, e)
            tlog.log_reviewer_eval(
                turn=turn.id,
                raw_scores={},
                parse_success=False,
                reviewer_provider=reviewer_config.provider,
                reviewer_model=reviewer_config.model,
                latency_ms=latency_ms,
            )
            tlog.log_error(
                context=f"subtest_1/reviewer_turn_{turn.id}",
                error_type=type(e).__name__,
                message=str(e),
                traceback=traceback.format_exc(),
            )

    subtest_1 = Subtest1(turns=turns, reviewer_scores=reviewer_scores)

    # -------------------------------------------------------------------
    # Subtest 2: Branching Choice (3 decision points)
    # -------------------------------------------------------------------
    choices: list[Choice] = []

    for dp in scenario.subtests.subtest_2.decision_points:
        # Build the prompt listing options
        options_list = [
            f"{key}: {opt.text}"
            for key, opt in dp.options.items()
        ]
        options_text = "\n".join(options_list)
        choice_prompt = f"{dp.prompt}\n\nOptions:\n{options_text}\n\nChoose A, B, or C. Respond with just the letter."
        messages = [
            {"role": "system", "content": scenario.system_prompt},
            {"role": "user", "content": choice_prompt},
        ]

        t0 = time.time()
        try:
            response = call_llm(
                provider=model_config.provider,
                model=model_config.model,
                api_key=model_config.api_key,
                api_base=model_config.api_base or None,
                messages=messages,
                max_tokens=model_config.max_tokens,
                temperature=model_config.temperature,
            )
            latency_ms = (time.time() - t0) * 1000
            tlog.log_llm_call(
                subtest="subtest_2",
                turn=None,
                provider=model_config.provider,
                model=model_config.model,
                prompt_preview=choice_prompt,
                response_preview=response,
                latency_ms=latency_ms,
                status="success",
            )
        except SkipModel:
            tlog.finish(status="failed")
            raise
        except LLMError as e:
            latency_ms = (time.time() - t0) * 1000
            all_succeeded = False
            logger.error("Model call failed on DP %s: %s", dp.id, e)
            tlog.log_llm_call(
                subtest="subtest_2",
                turn=None,
                provider=model_config.provider,
                model=model_config.model,
                prompt_preview=choice_prompt,
                response_preview=f"[ERROR: {e}]",
                latency_ms=latency_ms,
                status="error",
                error=str(e),
            )
            tlog.log_error(
                context=f"subtest_2/dp_{dp.id}",
                error_type="LLMError",
                message=str(e),
                traceback=traceback.format_exc(),
            )
            choices.append(Choice(dp=dp.id, choice="?"))
            tlog.log_choice(
                subtest="subtest_2",
                dp=dp.id,
                options=options_list,
                chosen="?",
                weights={},
            )
            continue

        # Parse choice
        selected = _parse_choice(response.strip(), list(dp.options.keys()))
        weights = dict(dp.options.get(selected, {}).weights) if selected in dp.options else {}
        choices.append(Choice(dp=dp.id, choice=selected, weights_applied=weights))
        tlog.log_choice(
            subtest="subtest_2",
            dp=dp.id,
            options=options_list,
            chosen=selected,
            weights=weights,
        )

    # Accumulate path weights
    path_weights = accumulate_weights(choices)
    subtest_2 = Subtest2(choices=choices, path_weights=path_weights)

    # -------------------------------------------------------------------
    # Subtest 3: Rigid Choice (final ultimatum)
    # -------------------------------------------------------------------
    options_list_3 = [
        f"{key}: {opt.text}"
        for key, opt in scenario.subtests.subtest_3.options.items()
    ]
    options_text = "\n".join(options_list_3)
    rigid_prompt = f"{scenario.subtests.subtest_3.prompt}\n\nOptions:\n{options_text}\n\nChoose 1, 2, or 3. Respond with just the number."
    messages = [
        {"role": "system", "content": scenario.system_prompt},
        {"role": "user", "content": rigid_prompt},
    ]

    t0 = time.time()
    try:
        response = call_llm(
            provider=model_config.provider,
            model=model_config.model,
            api_key=model_config.api_key,
            api_base=model_config.api_base or None,
            messages=messages,
            max_tokens=model_config.max_tokens,
            temperature=0.3,
        )
        latency_ms = (time.time() - t0) * 1000
        tlog.log_llm_call(
            subtest="subtest_3",
            turn=None,
            provider=model_config.provider,
            model=model_config.model,
            prompt_preview=rigid_prompt,
            response_preview=response,
            latency_ms=latency_ms,
            status="success",
        )
    except SkipModel:
        tlog.finish(status="failed")
        raise
    except LLMError as e:
        latency_ms = (time.time() - t0) * 1000
        all_succeeded = False
        logger.error("Model call failed on subtest 3: %s", e)
        response = "?"
        tlog.log_llm_call(
            subtest="subtest_3",
            turn=None,
            provider=model_config.provider,
            model=model_config.model,
            prompt_preview=rigid_prompt,
            response_preview=f"[ERROR: {e}]",
            latency_ms=latency_ms,
            status="error",
            error=str(e),
        )
        tlog.log_error(
            context="subtest_3",
            error_type="LLMError",
            message=str(e),
            traceback=traceback.format_exc(),
        )

    final_choice = _parse_choice(response.strip(), list(scenario.subtests.subtest_3.options.keys()))
    final_weights = (
        dict(scenario.subtests.subtest_3.options.get(final_choice, {}).weights)
        if final_choice and final_choice in scenario.subtests.subtest_3.options
        else {}
    )

    subtest_3 = Subtest3(choice=final_choice, weights_applied=final_weights)

    tlog.log_choice(
        subtest="subtest_3",
        dp=None,
        options=options_list_3,
        chosen=str(final_choice),
        weights=final_weights,
    )

    # -------------------------------------------------------------------
    # Scoring
    # -------------------------------------------------------------------
    gate = check_gate(reviewer_scores, path_weights, final_weights)
    failure_modes = detect_failure_modes(reviewer_scores, path_weights, final_weights)
    composite_score = compute_composite_score(reviewer_scores, path_weights, final_weights)

    # If gate fails, composite = 0
    if not gate.passed:
        composite_score = 0.0

    tlog.log_scoring(
        gate_passed=gate.passed,
        composite_score=composite_score,
        failure_modes=failure_modes.detected if hasattr(failure_modes, 'detected') else [],
        dv_weight=gate.actual_weight,
    )

    # ── Determine status ──────────────────────────────────────────────
    status = "completed" if all_succeeded else "partial"

    result = RunResult(
        run_id=run_id,
        model=model_config.model,
        scenario=scenario_id,
        defender=defender_variant,
        timestamp=datetime.now().isoformat(),
        status=status,
        subtest_1=subtest_1,
        subtest_2=subtest_2,
        subtest_3=subtest_3,
        gate=gate,
        failure_modes=failure_modes,
        composite_score=composite_score,
    )

    # Auto-save
    save_run_result(result, output_dir)

    # ── Finish logger ─────────────────────────────────────────────────
    tlog.finish(status=status)

    return result
def _parse_choice(response: str, valid_keys: list[str]) -> str:
    """Parse the model's choice from its response.

    Exact match first (look for key at start), then fuzzy contains check.
    """
    clean = response.strip().upper().rstrip(".")

    # Exact match
    if clean in valid_keys:
        return clean

    # Check if response starts with a valid key
    for key in valid_keys:
        if clean.startswith(key.upper()):
            return key

    # Contains match
    for key in valid_keys:
        if key.upper() in clean:
            return key

    logger.warning("Could not parse choice from: %s (valid: %s)", response, valid_keys)
    return "?"
