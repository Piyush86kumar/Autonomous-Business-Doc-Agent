"""FastAPI entry point — POST /agent, GET /files/{filename}."""

from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # load GROQ_API_KEY before any node imports

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

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

    # Re-validate snapshot into Pydantic model for type-safe access
    final_state = AgentState.model_validate(result)

    if not final_state.final_docx_path:
        raise HTTPException(status_code=500, detail="Agent completed but produced no document.")

    filename = Path(final_state.final_docx_path).name

    return AgentResponse(
        plan=final_state.plan_log,
        doc_type=final_state.doc_type,
        outline=final_state.outline,
        sections=final_state.sections,
        review=final_state.review,
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


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Serve the pipeline UI."""
    html_path = Path(__file__).parent / "templates" / "index.html"
    html_content = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=html_content)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
