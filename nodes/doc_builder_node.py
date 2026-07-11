"""LangGraph node wrapper around the doc_builder module."""

from __future__ import annotations

from doc_builder import build_document
from schemas import AgentState


def doc_builder_node(state: AgentState) -> dict:
    filepath = build_document(state)
    return {
        "final_docx_path": filepath,
        "plan_log": state.plan_log + ["Document generated."],
    }
