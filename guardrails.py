"""Pre-graph request validation — cheap deterministic checks before any LLM call."""

from __future__ import annotations

MIN_REQUEST_LENGTH = 8
MAX_REQUEST_LENGTH = 4000

# Small denylist for obviously unsafe/off-topic requests.
_UNSAFE_KEYWORDS = (
    "bomb", "explosive", "hack into", "malware", "ransomware",
    "kill", "weapon schematic",
)


class GuardrailViolation(ValueError):
    """Request validation failed."""


def validate_request(raw_request: str) -> str:
    """Validate and normalize an incoming request string."""
    cleaned = (raw_request or "").strip()

    if not cleaned:
        raise GuardrailViolation("Request cannot be empty.")

    if len(cleaned) < MIN_REQUEST_LENGTH:
        raise GuardrailViolation(
            "Request is too short to determine what document is needed. "
            "Please describe what you'd like produced in a sentence or two."
        )

    if len(cleaned) > MAX_REQUEST_LENGTH:
        raise GuardrailViolation(
            f"Request is too long ({len(cleaned)} chars). Please keep it under "
            f"{MAX_REQUEST_LENGTH} characters."
        )

    lowered = cleaned.lower()
    for kw in _UNSAFE_KEYWORDS:
        if kw in lowered:
            raise GuardrailViolation(
                "This request can't be processed by the document agent."
            )

    return cleaned
