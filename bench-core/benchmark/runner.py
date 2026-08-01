"""Scenario runner — runs one scenario with one model + defender variant."""

from __future__ import annotations

import logging
import re
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
    check_gate_v2,
    compute_composite_score,
    compute_resilience_depth,
    detect_failure_modes,)
from benchmark.storage import save_run_result, get_run_id

logger = logging.getLogger(__name__)


def run_scenario(
    model_config: LLMConfig,
    reviewer_config: LLMConfig,
    scenario: Scenario,
    defender_variant: str,
    output_dir: str = "./results",
    run_id: str | None = None,
    subtests: list[str] | None = None,
) -> RunResult:
    """Run a single scenario with one model + defender variant.

    Lifecycle:
    1. Subtest 1: Freeform Dialogue (3 turns) + AI reviewer evaluation
    2. Subtest 2: Branching Choice (3 decision points)
    3. Subtest 3: Rigid Choice (final ultimatum)
    4. Gate check + failure mode detection
    5. Composite score calculation
    6. Auto-save

    Args:
        subtests: Optional list of subtest names to run (e.g. ["subtest_1", "subtest_3"]).
                  If None (default), ALL subtests are run.
                  Skipped subtests produce empty objects that show
                  "unscored/untested" in the template output.
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

    # ── Determine which subtests to run ────────────────────────────────
    _run_all = subtests is None

    # ── Initialize conversation history ─────────────────────────────────
    defender_context = scenario.defender_variants.get(defender_variant, "")
    sys_content = scenario.system_prompt
    if defender_context:
        sys_content = sys_content + "\n\nAdditional context about the user's situation: " + defender_context
    conversation = [{"role": "system", "content": sys_content}]

    # -------------------------------------------------------------------
    # Subtest 1: Freeform Dialogue (3 turns)
    # -------------------------------------------------------------------
    turns: list[Turn] = []
    reviewer_scores = ReviewerScores()

    if _run_all or "subtest_1" in (subtests or []):
        for turn_def in scenario.subtests.subtest_1.turns:
            prompt = turn_def.prompt


            conversation.append({"role": "user", "content": prompt})

            t0 = time.time()
            try:
                response = call_llm(
                    provider=model_config.provider,
                    model=model_config.model,
                    api_key=model_config.api_key,
                    api_base=model_config.api_base or None,
                    messages=list(conversation),
                    max_tokens=model_config.max_tokens,
                    temperature=model_config.temperature,
                )
                latency_ms = (time.time() - t0) * 1000
                conversation.append({"role": "assistant", "content": response})
                tlog.log_llm_call(
                    subtest="subtest_1",
                    turn=turn_def.id,
                    provider=model_config.provider,
                    model=model_config.model,
                    prompt_full=prompt,
                    response_full=response,
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
                conversation.append({"role": "assistant", "content": "[Response unavailable due to model error]"})
                tlog.log_llm_call(
                    subtest="subtest_1",
                    turn=turn_def.id,
                    provider=model_config.provider,
                    model=model_config.model,
                    prompt_full=prompt,
                    response_full=response,
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

            # —— Review immediately after this turn ——
            t0 = time.time()
            try:
                result = review_response(
                    reviewer_config=reviewer_config,
                    scenario_id=scenario_id,
                    defender_variant=defender_variant,
                    turn=turn_def.id,
                    model_response=response,
                    conversation_history=list(conversation),
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
                    turn=turn_def.id,
                    raw_scores=raw_scores,
                    parse_success=True,
                    reviewer_provider=reviewer_config.provider,
                    reviewer_model=reviewer_config.model,
                    latency_ms=latency_ms,
                )

                # —— Early termination check ——
                if result.pass_task == "yes":
                    logger.info(
                        "Subtest 1 early termination: model complied at turn %d",
                        turn_def.id,
                    )
                    break
            except SkipModel:
                tlog.finish(status="failed")
                raise
            except Exception as e:
                latency_ms = (time.time() - t0) * 1000
                all_succeeded = False
                logger.error("Review failed for turn %d: %s", turn_def.id, e)
                tlog.log_reviewer_eval(
                    turn=turn_def.id,
                    raw_scores={},
                    parse_success=False,
                    reviewer_provider=reviewer_config.provider,
                    reviewer_model=reviewer_config.model,
                    latency_ms=latency_ms,
                )
                tlog.log_error(
                    context=f"subtest_1/reviewer_turn_{turn_def.id}",
                    error_type=type(e).__name__,
                    message=str(e),
                    traceback=traceback.format_exc(),
                )

    subtest_1 = Subtest1(turns=turns, reviewer_scores=reviewer_scores)

    # -------------------------------------------------------------------
    # Subtest 2: Branching Choice
    # -------------------------------------------------------------------
    choices: list[Choice] = []
    subtest_2_terminated: bool = False
    subtest_2_termination_node: str | None = None
    subtest_2_termination_reason: str | None = None
    subtest_2_path_taken: list[str] = []

    if _run_all or "subtest_2" in (subtests or []):
        # NEW: dialogue tree format
        if scenario.dialogue_tree is not None:
            tree = scenario.dialogue_tree.subtest_2
            current = tree.start_node

            while current is not None:
                if current not in tree.nodes:
                    logger.error("Node '%s' not found in dialogue tree", current)
                    break

                node = tree.nodes[current]

                if hasattr(node, 'options'):  # ChoiceNode
                    options_list = [f"{key}: {opt.text}" for key, opt in node.options.items()]
                    options_text = "\n".join(options_list)
                    choice_prompt = f"{node.prompt}\n\nOptions:\n{options_text}\n\nChoose A, B, or C. Respond with just the letter."
                    conversation.append({"role": "user", "content": choice_prompt})

                    t0 = time.time()
                    try:
                        response = call_llm(
                            provider=model_config.provider, model=model_config.model,
                            api_key=model_config.api_key, api_base=model_config.api_base or None,
                            messages=list(conversation),
                            max_tokens=model_config.max_tokens, temperature=model_config.temperature,
                        )
                        latency_ms = (time.time() - t0) * 1000
                        conversation.append({"role": "assistant", "content": response})
                        tlog.log_llm_call(subtest="subtest_2", turn=None, provider=model_config.provider,
                                         model=model_config.model, prompt_full=choice_prompt,
                                         response_full=response, latency_ms=latency_ms, status="success")
                    except SkipModel:
                        tlog.finish(status="failed")
                        raise
                    except LLMError as e:
                        latency_ms = (time.time() - t0) * 1000
                        all_succeeded = False
                        logger.error("Model call failed on node %s: %s", current, e)
                        conversation.append({"role": "assistant", "content": "[Response unavailable due to model error]"})
                        tlog.log_llm_call(subtest="subtest_2", turn=None, provider=model_config.provider,
                                         model=model_config.model, prompt_full=choice_prompt,
                                         response_full=f"[ERROR: {e}]", latency_ms=latency_ms, status="error", error=str(e))
                        tlog.log_error(context=f"subtest_2/node_{current}", error_type="LLMError",
                                      message=str(e), traceback=traceback.format_exc())
                        choices.append(Choice(dp=current, choice="?"))
                        tlog.log_choice(subtest="subtest_2", dp=current, options=options_list, chosen="?", weights={})
                        break

                    selected = _parse_choice(response.strip(), list(node.options.keys()))
                    chosen_option = node.options.get(selected)
                    weights = dict(chosen_option.weights) if chosen_option else {}
                    choices.append(Choice(dp=current, choice=selected, weights_applied=weights))
                    subtest_2_path_taken.append(f"{current}:{selected}")
                    tlog.log_choice(subtest="subtest_2", dp=current, options=options_list, chosen=selected, weights=weights)

                    if chosen_option and chosen_option.terminal:
                        subtest_2_terminated = True
                        subtest_2_termination_node = current
                        subtest_2_termination_reason = chosen_option.terminal_reason
                        logger.info("Subtest 2 terminated at node %s: %s", current, chosen_option.terminal_reason)
                        break

                    current = chosen_option.next if chosen_option else None

                elif hasattr(node, 'prompt') and hasattr(node, 'next'):  # PromptNode
                    conversation.append({"role": "user", "content": node.prompt})
                    t0 = time.time()
                    try:
                        response = call_llm(
                            provider=model_config.provider, model=model_config.model,
                            api_key=model_config.api_key, api_base=model_config.api_base or None,
                            messages=list(conversation),
                            max_tokens=model_config.max_tokens, temperature=model_config.temperature,
                        )
                        latency_ms = (time.time() - t0) * 1000
                        conversation.append({"role": "assistant", "content": response})
                        tlog.log_llm_call(subtest="subtest_2", turn=None, provider=model_config.provider,
                                         model=model_config.model, prompt_full=node.prompt,
                                         response_full=response, latency_ms=latency_ms, status="success")
                    except SkipModel:
                        tlog.finish(status="failed")
                        raise
                    except LLMError as e:
                        latency_ms = (time.time() - t0) * 1000
                        all_succeeded = False
                        conversation.append({"role": "assistant", "content": "[Response unavailable due to model error]"})

                    current = node.next

        # LEGACY: old format with decision_points list
        else:
            for dp in scenario.subtests.subtest_2.decision_points:
                # Build the prompt listing options
                options_list = [
                    f"{key}: {opt.text}"
                    for key, opt in dp.options.items()
                ]
                options_text = "\n".join(options_list)
                choice_prompt = f"{dp.prompt}\n\nOptions:\n{options_text}\n\nChoose A, B, or C. Respond with just the letter."
                conversation.append({"role": "user", "content": choice_prompt})

                t0 = time.time()
                try:
                    response = call_llm(
                        provider=model_config.provider,
                        model=model_config.model,
                        api_key=model_config.api_key,
                        api_base=model_config.api_base or None,
                        messages=list(conversation),
                        max_tokens=model_config.max_tokens,
                        temperature=model_config.temperature,
                    )
                    latency_ms = (time.time() - t0) * 1000
                    conversation.append({"role": "assistant", "content": response})
                    tlog.log_llm_call(
                        subtest="subtest_2",
                        turn=None,
                        provider=model_config.provider,
                        model=model_config.model,
                        prompt_full=choice_prompt,
                        response_full=response,
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
                    conversation.append({"role": "assistant", "content": "[Response unavailable due to model error]"})
                    tlog.log_llm_call(
                        subtest="subtest_2",
                        turn=None,
                        provider=model_config.provider,
                        model=model_config.model,
                        prompt_full=choice_prompt,
                        response_full=f"[ERROR: {e}]",
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
    if scenario.dialogue_tree is not None:
        # NEW: dialogue tree format
        tree = scenario.dialogue_tree.subtest_3
        node = tree.nodes[tree.start_node]  # subtest_3 has a single choice node

        if hasattr(node, 'options'):  # ChoiceNode
            options_list_3 = [f"{key}: {opt.text}" for key, opt in node.options.items()]
            options_text = "\n".join(options_list_3)
            rigid_prompt = f"{node.prompt}\n\nOptions:\n{options_text}\n\nChoose 1, 2, or 3. Respond with just the number."
        else:
            options_text = ""
            rigid_prompt = node.prompt
            options_list_3 = []

        if _run_all or "subtest_3" in (subtests or []):
            conversation.append({"role": "user", "content": rigid_prompt})
            t0 = time.time()
            try:
                response = call_llm(
                    provider=model_config.provider, model=model_config.model,
                    api_key=model_config.api_key, api_base=model_config.api_base or None,
                    messages=list(conversation),
                    max_tokens=model_config.max_tokens, temperature=model_config.temperature,
                )
                latency_ms = (time.time() - t0) * 1000
                conversation.append({"role": "assistant", "content": response})
                tlog.log_llm_call(subtest="subtest_3", turn=None, provider=model_config.provider,
                                 model=model_config.model, prompt_full=rigid_prompt,
                                 response_full=response, latency_ms=latency_ms, status="success")
            except SkipModel:
                tlog.finish(status="failed")
                raise
            except LLMError as e:
                latency_ms = (time.time() - t0) * 1000
                all_succeeded = False
                logger.error("Model call failed on subtest 3: %s", e)
                response = "?"
                conversation.append({"role": "assistant", "content": "[Response unavailable due to model error]"})
                tlog.log_llm_call(subtest="subtest_3", turn=None, provider=model_config.provider,
                                 model=model_config.model, prompt_full=rigid_prompt,
                                 response_full=f"[ERROR: {e}]", latency_ms=latency_ms, status="error", error=str(e))
                tlog.log_error(context="subtest_3", error_type="LLMError", message=str(e),
                              traceback=traceback.format_exc())
        else:
            response = "?"

        if hasattr(node, 'options'):
            valid_keys = list(node.options.keys())
            final_choice = _parse_choice(response.strip(), valid_keys)
            chosen_option = node.options.get(final_choice)
            final_weights = dict(chosen_option.weights) if chosen_option else {}
        else:
            final_choice = "?"
            final_weights = {}

        subtest_3 = Subtest3(choice=final_choice, weights_applied=final_weights)

        tlog.log_choice(subtest="subtest_3", dp=None, options=options_list_3,
                       chosen=str(final_choice), weights=final_weights)
    else:
        # LEGACY: old format with decision_points list
        options_list_3 = [
            f"{key}: {opt.text}"
            for key, opt in scenario.subtests.subtest_3.options.items()
        ]
        options_text = "\n".join(options_list_3)
        rigid_prompt = f"{scenario.subtests.subtest_3.prompt}\n\nOptions:\n{options_text}\n\nChoose 1, 2, or 3. Respond with just the number."

        if _run_all or "subtest_3" in (subtests or []):
            conversation.append({"role": "user", "content": rigid_prompt})
            t0 = time.time()
            try:
                response = call_llm(
                    provider=model_config.provider,
                    model=model_config.model,
                    api_key=model_config.api_key,
                    api_base=model_config.api_base or None,
                    messages=list(conversation),
                    max_tokens=model_config.max_tokens,
                    temperature=model_config.temperature,
                )
                latency_ms = (time.time() - t0) * 1000
                conversation.append({"role": "assistant", "content": response})
                tlog.log_llm_call(
                    subtest="subtest_3",
                    turn=None,
                    provider=model_config.provider,
                    model=model_config.model,
                    prompt_full=rigid_prompt,
                    response_full=response,
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
                conversation.append({"role": "assistant", "content": "[Response unavailable due to model error]"})
                tlog.log_llm_call(
                    subtest="subtest_3",
                    turn=None,
                    provider=model_config.provider,
                    model=model_config.model,
                    prompt_full=rigid_prompt,
                    response_full=f"[ERROR: {e}]",
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
        else:
            response = "?"

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
    # Determine terminal reason (model_complied from any subtest)
    terminal_reason = subtest_2_termination_reason

    # Use v2 gate if dialogue tree format
    if scenario.dialogue_tree is not None:
        gate = check_gate_v2(terminal_reason)
        # Compute resilience depth
        subtest_2_total = len(scenario.dialogue_tree.subtest_2.nodes) if scenario.dialogue_tree is not None else 0
        subtest_2_visited = len(subtest_2_path_taken)
        resilience_depth = compute_resilience_depth(subtest_2_visited, subtest_2_total, True)
        any_compliance = terminal_reason == "model_complied"
    else:
        # Legacy gate check (unchanged)
        gate = check_gate(reviewer_scores, path_weights, final_weights)
        resilience_depth = 1.0
        any_compliance = not gate.passed

    failure_modes = detect_failure_modes(reviewer_scores, path_weights, final_weights)
    composite_score = compute_composite_score(reviewer_scores, path_weights, final_weights)

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
        subtest_2_terminated=subtest_2_terminated,
        subtest_2_termination_node=subtest_2_termination_node,
        subtest_2_termination_reason=subtest_2_termination_reason,
        subtest_2_path_taken=subtest_2_path_taken,
        resilience_depth=resilience_depth,
        any_compliance=any_compliance,
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

    # Contains match (word-boundary)
    for key in valid_keys:
        if re.search(rf'\b{re.escape(key)}\b', clean, re.IGNORECASE):
            return key

    logger.warning("Could not parse choice from: %s (valid: %s)", response, valid_keys)
    return "?"
