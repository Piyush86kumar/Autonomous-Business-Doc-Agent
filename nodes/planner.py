"""Planner node — infers document type and sections from the raw request."""

from __future__ import annotations

from llm_client import structured_call
from schemas import AgentState, OutlineSchema

SYSTEM_PROMPT = """You are a Business Document Strategist. Given a natural
language request from a user, decide:

1. What TYPE of business document best fits the request. Common types include
   project_proposal, meeting_minutes, project_plan, sop (standard operating
   procedure), technical_design, product_specification, business_report — but
   you are not limited to this list; pick whatever type genuinely fits.

2. A professional title for the document.

3. A list of sections needed to fully address the request. For each section,
   give a short name and a one-sentence purpose. Mark needs_table=true only
   for sections that naturally contain structured line-item data (e.g. a
   budget breakdown or a timeline with dates/milestones).

If the request is ambiguous, vague, or missing information (e.g. no stated
budget, timeline, or audience), do NOT invent specifics. Instead, plan
sections that are appropriate for what WAS stated, and rely on later stages
of the pipeline to flag what's missing. Prefer fewer, well-justified sections
over padding the outline with sections the request doesn't support.
"""


def planner_node(state: AgentState) -> dict:
    outline: OutlineSchema = structured_call(
        schema=OutlineSchema,
        system_prompt=SYSTEM_PROMPT,
        user_content=state.original_request,
    )

    section_names = ", ".join(s.section_name for s in outline.sections)
    log_entry = (
        f"Classified request as: {outline.doc_type}. "
        f"Planned sections: {section_names}."
    )

    return {
        "doc_type": outline.doc_type,
        "outline": outline,
        "plan_log": state.plan_log + [log_entry],
    }
