"""LangGraph StateGraph — planner → writer → reviewer → doc_builder with revision loop."""

from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from nodes.planner import planner_node
from nodes.writer import writer_node
from nodes.reviewer import reviewer_node, MAX_REVISIONS
from nodes.doc_builder_node import doc_builder_node
from schemas import AgentState


def _route_after_review(state: AgentState) -> str:
    """Route back to writer if needs_revision and under cap, else finalize."""
    if (
        state.review is not None
        and state.review.verdict == "needs_revision"
        and state.revision_count <= MAX_REVISIONS
    ):
        return "writer"
    return "doc_builder"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("planner", planner_node)
    graph.add_node("writer", writer_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("doc_builder", doc_builder_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "writer")
    graph.add_edge("writer", "reviewer")

    graph.add_conditional_edges(
        "reviewer",
        _route_after_review,
        {"writer": "writer", "doc_builder": "doc_builder"},
    )

    graph.add_edge("doc_builder", END)

    return graph.compile()


# Compiled once at import time and reused across requests.
compiled_graph = build_graph()
