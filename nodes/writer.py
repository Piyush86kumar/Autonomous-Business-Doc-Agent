"""Writer node — drafts one LLM call per section, passes short summaries forward, addresses revision gaps."""

from __future__ import annotations

from llm_client import structured_call
from schemas import AgentState, SectionSchema

SYSTEM_PROMPT_TEMPLATE = """You are a Content Drafter for professional business
documents. Draft the content for ONE section of a "{doc_type}" document
titled "{title}".

Section to draft: "{section_name}"
Purpose of this section: {purpose}

Original user request (for grounding — do not repeat it verbatim, use it to
inform what this section should say):
{original_request}

Context already covered in other sections of this document (do not repeat
this content, just stay consistent with it):
{prior_summaries}
{revision_context}
Write clear, professional, concise business prose (or well-structured bullet
points if more appropriate for this section type). Do NOT fabricate specific
numbers, names, or dates that were not given in the original request or
already established elsewhere in the document — if a concrete figure is
genuinely necessary and wasn't provided, write the section in a way that
notes it as TBD / to be confirmed, rather than inventing a plausible-sounding
number.
"""

REVISION_NOTE_TEMPLATE = """
This is a REVISION pass. The reviewer flagged the following gaps in the
previous draft — address any of these that are relevant to THIS section:
{gaps}
"""


def _summarize(content: str, max_words: int = 20) -> str:
    """Cheap, deterministic summary — no extra LLM call needed."""
    words = content.split()
    if len(words) <= max_words:
        return content.strip()
    return " ".join(words[:max_words]).strip() + "..."


def writer_node(state: AgentState) -> dict:
    assert state.outline is not None, "Writer node requires a planned outline"

    is_revision = state.review is not None and state.review.verdict == "needs_revision"
    gaps_text = "\n".join(f"- {g}" for g in state.review.gaps) if (is_revision and state.review) else ""
    revision_context = REVISION_NOTE_TEMPLATE.format(gaps=gaps_text) if is_revision else ""

    new_sections: dict[str, SectionSchema] = {}
    new_summaries: dict[str, str] = {}

    for planned in state.outline.sections:
        prior_summaries_text = "\n".join(
            f"- {name}: {summary}" for name, summary in new_summaries.items()
        ) or "(this is the first section)"

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            doc_type=state.outline.doc_type,
            title=state.outline.title,
            section_name=planned.section_name,
            purpose=planned.purpose,
            original_request=state.original_request,
            prior_summaries=prior_summaries_text,
            revision_context=revision_context,
        )

        section: SectionSchema = structured_call(
            schema=SectionSchema,
            system_prompt=system_prompt,
            user_content=f"Draft the '{planned.section_name}' section now.",
        )
        section.needs_table = planned.needs_table  # trust the Planner's structural call over the Writer's

        new_sections[planned.section_name] = section
        new_summaries[planned.section_name] = _summarize(section.content)

    log_entry = (
        "Redrafted all sections addressing reviewer feedback."
        if is_revision else
        "Drafted all planned sections."
    )

    return {
        "sections": new_sections,
        "section_summaries": new_summaries,
        "plan_log": state.plan_log + [log_entry],
    }
