"""Request/response, structured LLM output, and LangGraph state models."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# 1. API contracts

class AgentRequest(BaseModel):
    request: str = Field(..., min_length=1, description="Natural language business request")


class AgentResponse(BaseModel):
    plan: list[str] = Field(default_factory=list, description="Human-readable task list, for demo visibility")
    doc_type: str
    outline: Optional[OutlineSchema] = Field(
        default=None,
        description="Full outline produced by the Planner node — doc_type, title, sections list",
    )
    sections: dict[str, SectionSchema] = Field(
        default_factory=dict,
        description="Drafted content per section, keyed by section_name",
    )
    review: Optional[ReviewSchema] = Field(
        default=None,
        description="Reviewer node output — verdict, gaps, and assumptions identified",
    )
    assumptions_made: list[str] = Field(default_factory=list)
    revision_occurred: bool = False
    download_url: str
    message: str


# 2. Structured LLM outputs

class SectionPlan(BaseModel):
    """A single planned section, before it has been drafted."""
    section_name: str = Field(..., description="Short section title, e.g. 'Budget'")
    purpose: str = Field(..., description="One sentence describing what this section must cover")
    needs_table: bool = Field(
        default=False,
        description="True if this section should render as a table instead of prose",
    )


class OutlineSchema(BaseModel):
    """Planner node output."""
    doc_type: str = Field(
        ...,
        description="Inferred business document type (e.g. project_proposal, meeting_minutes, sop)",
    )
    title: str = Field(..., description="A professional title for the document")
    sections: list[SectionPlan] = Field(..., min_length=1)


class SectionSchema(BaseModel):
    """Writer node output, one per section."""
    section_name: str
    content: str = Field(..., description="Full drafted prose (or bullet content) for this section")
    needs_table: bool = False


class ReviewSchema(BaseModel):
    """Reviewer node output."""
    verdict: Literal["approved", "needs_revision"]
    gaps: list[str] = Field(
        default_factory=list,
        description="Missing info, contradictions, or unclear points in the draft",
    )
    assumptions_made: list[str] = Field(
        default_factory=list,
        description="Assumptions the draft makes to fill gaps not resolvable from the request",
    )


# 3. LangGraph state

class AgentState(BaseModel):
    """Single source of truth — LangGraph merges partial updates into this."""

    original_request: str

    doc_type: str = ""
    outline: Optional[OutlineSchema] = None

    sections: dict[str, SectionSchema] = Field(default_factory=dict)
    section_summaries: dict[str, str] = Field(default_factory=dict)

    review: Optional[ReviewSchema] = None
    revision_count: int = 0

    assumptions_made: list[str] = Field(default_factory=list)
    plan_log: list[str] = Field(default_factory=list)  # human-readable trace

    final_docx_path: Optional[str] = None
