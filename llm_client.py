"""Groq LLM client with primary + fallback model retry logic."""

from __future__ import annotations

import logging
import os
import time
from functools import lru_cache
from typing import Type, TypeVar

from langchain_groq import ChatGroq
from pydantic import BaseModel

logger = logging.getLogger("doc_agent.llm_client")

PRIMARY_MODEL = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "openai/gpt-oss-120b"

T = TypeVar("T", bound=BaseModel)


class LLMCallError(RuntimeError):
    """Raised when both primary and fallback model calls fail."""


@lru_cache(maxsize=8)
def _get_chat_model(model_name: str, temperature: float = 0.3) -> ChatGroq:
    """Cached ChatGroq client. GROQ_API_KEY loaded at call time, not import time."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Export it or add it to a .env file "
            "before starting the server."
        )
    return ChatGroq(model=model_name, api_key=api_key, temperature=temperature)


def structured_call(
    schema: Type[T],
    system_prompt: str,
    user_content: str,
    *,
    temperature: float = 0.3,
    max_retries_per_model: int = 2,
) -> T:
    """Call LLM with structured output and fallback retry across primary and backup models."""
    last_exception: Exception | None = None

    for model_name in (PRIMARY_MODEL, FALLBACK_MODEL):
        llm = _get_chat_model(model_name, temperature=temperature)
        structured_llm = llm.with_structured_output(schema)

        for attempt in range(1, max_retries_per_model + 1):
            try:
                result = structured_llm.invoke(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ]
                )
                if model_name == FALLBACK_MODEL:
                    logger.warning("Fell back to %s after primary model failures", model_name)
                return result  # type: ignore[return-value]

            except Exception as exc:  # noqa: BLE001
                last_exception = exc
                logger.warning(
                    "LLM call failed (model=%s, attempt=%d/%d): %s",
                    model_name, attempt, max_retries_per_model, exc,
                )
                # Simple exponential backoff
                time.sleep(1.5 * attempt)

    raise LLMCallError(
        f"All LLM attempts failed across primary ({PRIMARY_MODEL}) and "
        f"fallback ({FALLBACK_MODEL}) models. Last error: {last_exception}"
    )
