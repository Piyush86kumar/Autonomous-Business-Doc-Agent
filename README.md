# Autonomous Document Agent

A FastAPI service that accepts a natural-language business request, autonomously plans its own structure via a LangGraph state machine (Planner → Writer → Reviewer → Doc Builder, with a conditional revision loop), and returns a polished `.docx` file.

![Project Architecture](asset/autonomous_doc_agent.png)

### Technologies Used

| Category | Tools |
|---|---|
| **Framework** | FastAPI, Uvicorn |
| **Graph State Machine** | LangGraph |
| **LLM Provider** | Groq (free tier) |
| **Models** | `llama-3.3-70b-versatile`, `openai/gpt-oss-120b` (fallback) |
| **Structured Output** | Pydantic, `with_structured_output` |
| **Document Assembly** | `python-docx` |
| **Validation** | Pydantic, custom guardrails |

## 1. Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# edit .env and paste a free Groq API key from https://console.groq.com/keys
```

## 2. Run

```bash
uvicorn main:app --reload
```

The API is live at `http://127.0.0.1:8000`. Interactive docs (Swagger UI) at `http://127.0.0.1:8000/docs`.

## 3. Test Case 1 — Standard Request

```bash
curl -X POST http://127.0.0.1:8000/agent \
  -H "Content-Type: application/json" \
  -d '{
    "request": "Create a project proposal for migrating our internal tools from spreadsheets to a new CRM system (evaluating HubSpot vs Salesforce). Timeline is 3 months starting next quarter, budget is $50k, and the primary goal is reducing manual data entry for the sales team of 12 people. Include a rollout plan and key risks."
  }'
```

Response:
```json
{
  "plan": ["Classified request as: project_proposal. Planned sections: ...", "Drafted all planned sections.", "Reviewed draft — verdict: approved."],
  "doc_type": "project_proposal",
  "assumptions_made": [],
  "revision_occurred": false,
  "download_url": "/files/project_proposal_20260711_143210.docx",
  "message": "Generated a project proposal covering 5 section(s)."
}
```

Expected: `doc_type` is `"project_proposal"`, `assumptions_made` is empty, `revision_occurred` is `false` — everything needed was stated up front.

## 4. Test Case 2 — Ambiguous Request

```bash
curl -X POST http://127.0.0.1:8000/agent \
  -H "Content-Type: application/json" \
  -d '{
    "request": "Need something to send the client after today's call. Sales said we could do the integration in 3 weeks, but engineering mentioned on Slack it's more like 6-8 weeks realistically — not sure which number to use. Client hasn't confirmed budget yet either. Not sure if they want a formal proposal or just a quick summary of next steps, and my manager wants it before end of day."
  }'
```

Expected: the Planner infers a document type despite no explicit instruction, the Reviewer flags missing budget/timeline as gaps, and the final `.docx` includes an **Assumptions Made** section disclosing what was inferred rather than silently fabricating specifics.

## 5. Download the Generated Document

Both responses include a `download_url` field, e.g. `/files/project_proposal_20260711_143210.docx`:

```bash
curl -O -J http://127.0.0.1:8000/files/project_proposal_20260711_143210.docx
```

## 6. Project Structure

```
├── main.py                    # FastAPI app: POST /agent, GET /files/{filename}
├── schemas.py                 # Pydantic: API contracts, structured LLM outputs, AgentState
├── graph.py                   # LangGraph StateGraph wiring + conditional revision edge
├── guardrails.py              # Pre-graph request validation (length, unsafe keywords)
├── llm_client.py              # Groq client with primary/fallback model retry
├── doc_builder.py             # Deterministic python-docx assembly (not an LLM node)
├── nodes/
│   ├── planner.py             # Infers doc type and produces structured outline
│   ├── writer.py              # Drafts each section (context-flat, revision-aware)
│   ├── reviewer.py            # Independent quality check + revision loop guard
│   └── doc_builder_node.py    # Thin graph adapter for doc_builder.py
├── requirements.txt
├── .env.example
└── outputs/                   # Generated .docx files land here
```

## 7. One Improvement: Reflection / Self-Check with Revision Loop

Implemented as the Reviewer node + a LangGraph conditional edge back to the Writer, capped at one revision pass. The Reviewer runs with a **deliberately scoped context** — it sees only the original request and the final draft, never the Planner's or Writer's intermediate reasoning — which mimics an independent critic rather than the same model grading its own work.

Paired with lightweight **retry & fallback** in `llm_client.py`: every LLM call tries `llama-3.3-70b-versatile` first and falls back to `openai/gpt-oss-120b` (same provider, same free tier) on rate-limiting or failure.

## 8. Notes on Free-Tier Limits

Groq's free tier (`llama-3.3-70b-versatile`): 30 RPM / 1,000 RPD / 12K TPM / 100K TPD. A full document run uses roughly 6–8 LLM calls (one per section plus Planner and Reviewer). Verify current limits at `console.groq.com/settings/limits` before recording a demo, since free-tier numbers shift over time.
