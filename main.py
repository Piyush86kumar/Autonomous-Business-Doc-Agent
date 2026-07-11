"""
FastAPI application entry point.

    POST /agent   { "request": "<natural language>" }  -> AgentResponse
    GET  /files/{filename}                              -> download the .docx

Run with:  uvicorn main:app --reload
"""

from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # populates GROQ_API_KEY from .env before any node runs

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from doc_builder import OUTPUT_DIR
from graph import compiled_graph
from guardrails import GuardrailViolation, validate_request
from llm_client import LLMCallError
from schemas import AgentRequest, AgentResponse, AgentState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("doc_agent.main")

app = FastAPI(
    title="Autonomous Document Agent",
    description=(
        "Accepts a natural-language business request, autonomously plans, "
        "drafts, and reviews a structured document, and returns a polished "
        ".docx file."
    ),
    version="1.0.0",
)


@app.post("/agent", response_model=AgentResponse)
async def run_agent(payload: AgentRequest) -> AgentResponse:
    try:
        cleaned_request = validate_request(payload.request)
    except GuardrailViolation as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    initial_state = AgentState(original_request=cleaned_request)

    try:
        result = await compiled_graph.ainvoke(initial_state)
    except LLMCallError as exc:
        logger.error("LLM pipeline failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=(
                "The document agent could not complete this request because "
                "the LLM provider was unavailable after retries. Please try "
                "again shortly."
            ),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in agent pipeline")
        raise HTTPException(status_code=500, detail=f"Internal agent error: {exc}") from exc

    # LangGraph returns a dict-shaped state snapshot from ainvoke; re-validate
    # into our Pydantic model for type-safe attribute access below.
    final_state = AgentState.model_validate(result)

    if not final_state.final_docx_path:
        raise HTTPException(status_code=500, detail="Agent completed but produced no document.")

    filename = Path(final_state.final_docx_path).name

    return AgentResponse(
        plan=final_state.plan_log,
        doc_type=final_state.doc_type,
        assumptions_made=final_state.assumptions_made,
        revision_occurred=final_state.revision_count > 0,
        download_url=f"/files/{filename}",
        message=(
            f"Generated a {final_state.doc_type.replace('_', ' ')} "
            f"covering {len(final_state.sections)} section(s)."
            + (
                f" {len(final_state.assumptions_made)} assumption(s) were made "
                f"and disclosed in the document."
                if final_state.assumptions_made else ""
            )
        ),
    )


@app.get("/files/{filename}")
async def download_file(filename: str) -> FileResponse:
    filepath = (OUTPUT_DIR / filename).resolve()

    # Prevent path traversal outside the outputs directory.
    if OUTPUT_DIR.resolve() not in filepath.parents:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
