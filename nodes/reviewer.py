"""Reviewer node — independent quality check against the original request, with revision loop."""

from __future__ import annotations

from llm_client import structured_call
from schemas import AgentState, ReviewSchema

MAX_REVISIONS = 1

SYSTEM_PROMPT = """You are an independent Quality & Completeness Reviewer for
business documents. You did NOT write this draft — review it with fresh eyes
against the ORIGINAL request only.

Check for:
- Missing information the request implies is needed (budget, timeline,
  owner, scope, audience, etc.) that no section actually addresses
- Internal contradictions between sections
- Vague placeholders where a real business document would need specifics
- Anything the request explicitly asked for that isn't covered anywhere

If everything reasonably needed is present given what the ORIGINAL request
actually specified, verdict = "approved" — do not invent gaps that don't
matter just to find something to say. Business documents are allowed to be
appropriately brief when the request was brief.

If verdict = "needs_revision", list concrete, specific gaps (not vague
feedback) so a writer can act on them directly.

Separately, list assumptions_made: things the draft (reasonably) assumed
because the original request didn't specify them. Include these even if the
verdict is "approved" — the goal is transparency about what was inferred
versus what was explicitly requested.
"""


def _render_draft_for_review(state: AgentState) -> str:
    assert state.outline is not None
    parts = [f"Document type: {state.outline.doc_type}", f"Title: {state.outline.title}", ""]
    for planned in state.outline.sections:
        section = state.sections.get(planned.section_name)
        if section:
            parts.append(f"## {section.section_name}\n{section.content}\n")
    return "\n".join(parts)


def reviewer_node(state: AgentState) -> dict:
    draft_text = _render_draft_for_review(state)

    user_content = (
        f"ORIGINAL REQUEST:\n{state.original_request}\n\n"
        f"DRAFT TO REVIEW:\n{draft_text}"
    )

    review: ReviewSchema = structured_call(
        schema=ReviewSchema,
        system_prompt=SYSTEM_PROMPT,
        user_content=user_content,
    )

    new_revision_count = state.revision_count
    if review.verdict == "needs_revision":
        new_revision_count = state.revision_count + 1

    log_entry = (
        f"Reviewed draft — verdict: {review.verdict}."
        + (f" Gaps found: {len(review.gaps)}." if review.gaps else "")
    )

    # Merge de-duplicated assumptions into state
    merged_assumptions = list(dict.fromkeys(state.assumptions_made + review.assumptions_made))

    return {
        "review": review,
        "revision_count": new_revision_count,
        "assumptions_made": merged_assumptions,
        "plan_log": state.plan_log + [log_entry],
    }
