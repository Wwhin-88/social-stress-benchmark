"""LLM call wrapper around litellm with retry and error handling."""

from __future__ import annotations

import logging
import time
from typing import Any

import litellm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
TIMEOUT = 15000  # seconds (local models like Nemotron on M1 need 60-90s)
BASE_DELAY = 1.0


class LLMError(Exception):
    """Base exception for LLM call failures."""
    pass


class TimeoutError_(LLMError):
    """LLM call timed out."""
    pass


class AuthError(LLMError):
    """Authentication/API key error."""
    pass


class SkipModel(Exception):
    """Raised when a model should be skipped entirely."""
    pass


# ---------------------------------------------------------------------------
# Model call
# ---------------------------------------------------------------------------

def call_llm(
    provider: str,
    model: str,
    api_key: str,
    messages: list[dict[str, str]],
    max_tokens: int | None = None,
    temperature: float | None = None,
    timeout: int = TIMEOUT,
    api_base: str | None = None,
) -> str:
    """Call an LLM with retry logic. Returns the response text.

    Supports all providers through litellm.
    Handles: timeout, auth errors, rate limits, network errors.
    timeout: seconds before retry (default TIMEOUT=120).
    api_base: optional custom endpoint (for local models, openrouter, etc.)
    max_tokens / temperature: if None, use provider defaults.
    """
    # Map "local" → "openai" — litellm has no "local" provider.
    # Local servers (LM Studio, vLLM, Ollama) are OpenAI-compatible.
    if provider and provider.lower() == "local":
        provider = "openai"
        if not api_key:
            api_key = "not-needed"

    model_string = f"{provider}/{model}" if provider else model

    # Build kwargs — only pass non-None overrides
    kwargs: dict = {}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if temperature is not None:
        kwargs["temperature"] = temperature

    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = litellm.completion(
                model=model_string,
                api_key=api_key,
                messages=messages,
                timeout=timeout,
                api_base=api_base or None,
                **kwargs,
            )
            return response.choices[0].message.content or ""

        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            # Add api_base context for easier debugging
            if api_base and "api_base" not in error_str:
                error_str += f" [api_base={api_base}]"

            # Authentication error — no point retrying
            if any(kw in error_str for kw in ("auth", "api_key", "api key", "unauthorized", "403", "401")):
                raise SkipModel(f"Authentication failed for {model_string}: {e}") from e

            # Timeout — retry
            if any(kw in error_str for kw in ("timeout", "timed out", "time out")):
                if attempt < MAX_RETRIES:
                    delay = BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Timeout calling %s (attempt %d/%d), retrying in %.1fs...",
                        model_string, attempt + 1, MAX_RETRIES, delay,
                    )
                    time.sleep(delay)
                    continue
                raise TimeoutError_(f"Timeout calling {model_string} after {MAX_RETRIES} retries") from e

            # Rate limit — retry
            if any(kw in error_str for kw in ("rate", "429", "too many")):
                if attempt < MAX_RETRIES:
                    delay = BASE_DELAY * (2 ** attempt) * 2
                    logger.warning(
                        "Rate limited on %s (attempt %d/%d), retrying in %.1fs...",
                        model_string, attempt + 1, MAX_RETRIES, delay,
                    )
                    time.sleep(delay)
                    continue
                raise LLMError(f"Rate limit exceeded for {model_string}") from e

            # Network error — retry
            if any(kw in error_str for kw in ("connection", "network", "reset", "refused")):
                if attempt < MAX_RETRIES:
                    delay = BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Network error on %s (attempt %d/%d), retrying in %.1fs...",
                        model_string, attempt + 1, MAX_RETRIES, delay,
                    )
                    time.sleep(delay)
                    continue
                raise LLMError(f"Network error calling {model_string} after {MAX_RETRIES} retries") from e

            # Other error — fail fast on last attempt
            if attempt >= MAX_RETRIES:
                raise LLMError(f"Failed to call {model_string}: {e}") from e

            # Generic retry
            delay = BASE_DELAY * (2 ** attempt)
            logger.warning(
                "Error calling %s (attempt %d/%d): %s. Retrying in %.1fs...",
                model_string, attempt + 1, MAX_RETRIES, e, delay,
            )
            time.sleep(delay)

    raise LLMError(f"Failed to call {model_string}: {last_error}")
