# Case-triage-ai-agent

## Overview

This repository implements a small CRM duplicate investigation system with:

- deterministic candidate-pair generation from a messy CRM export
- an autonomous AI agent that chooses tools, gathers evidence, and drafts a recommendation
- a human-in-the-loop approval gate enforced by a REST API
- an audit trail saved in SQLite and exposed via API

The agent uses Google Gemini (`gemini-3.5-flash-lite`) through `google.generativeai`.

## Model Used

- Google Gemini 3.5 Flash Lite
- Google AI Studio
- `google-generativeai` SDK

## Time Spent

Approximately 5 hours.

## Agent Design

The system separates deterministic Python logic from LLM reasoning.

The LLM decides:

- Which tool to execute next
- Whether enough evidence has been gathered
- The final recommendation

The Python code decides:

- Maximum reasoning steps
- Tool execution and ordering
- Schema validation for model responses
- Retry and rate-limit handling
- Human approval enforcement via the backend

## Output Schema

```json
{
  "verdict": "DUPLICATE" | "NOT_DUPLICATE" | "UNSURE",
  "confidence": 0.0,
  "evidence": ["string"]
}
```

## Loop Bound

The investigation loop is bounded by `MAX_STEPS` to prevent infinite reasoning loops.

## Repository structure

- `app/`
  - `agent.py` — the investigation agent loop and tool orchestration
  - `api.py` — FastAPI endpoints for reviewing investigations and recording human decisions
  - `candidate_generator.py` — deterministic candidate-pair generation rules
  - `candidate_ranker.py` — deterministic scoring and bucket assignment
  - `database.py` — SQLite storage and audit helpers
  - `main.py` — batch driver for generating candidates, running top cases through the agent, and persisting investigations
  - `models.py` — Pydantic schemas for tool requests, verdicts, and agent state
  - `prompts.py` — prompt templates for tool selection and final verdict
  - `tools.py` — deterministic helper tools used by the agent
- `data/support_cases.csv` — input CRM case dataset
- `crm_agent.db` — generated at runtime SQLite database
- `logs/` — generated at runtime log files
- `.env` — environment variables (must include `GOOGLE_API_KEY`)
- `requirements.txt` — Python dependencies

## Setup

## Requirements

- Python 3.11+
- Google Gemini API Key
- Internet connection (for Gemini API)

### 1. Create a Python virtual environment

```bash
python -m venv venv
```

### 2. Activate the environment

Windows PowerShell:

```powershell
venv\Scripts\Activate.ps1
```

Git Bash / macOS / Linux:

```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Add your API key

Create a `.env` file in the repo root with:

```env
GOOGLE_API_KEY=YOUR_GOOGLE_API_KEY
```

> Do not commit your API key. Replace the existing value in `.env` with your own.

## Running the batch investigation flow

This repository supports a batch AI investigation run that:

1. loads `data/support_cases.csv`
2. generates candidate pairs
3. ranks candidates
4. runs the agent on the top candidate pairs
5. saves investigations to SQLite and logs

For this assignment, the pipeline investigates the top 10 highest-priority candidate pairs end-to-end.

Run:

```bash
python -m app.main
```

Expected output:

- `logs/candidate_generation.txt`
- `logs/agent_investigation.txt`
- `crm_agent.db`

If the script completes, it will print the number of raw and high-priority candidates and the investigation summary.

## Running the API

The API exposes investigation review endpoints and a Swagger UI.

Start the API server:

```bash
uvicorn app.api:app --reload --port 8000
```

Then open:

- `http://127.0.0.1:8000/docs` — Swagger UI
- `http://127.0.0.1:8000/redoc` — Redoc

## API Endpoints

### List pending investigations

```http
GET /investigations
```

Returns all investigations with status `PENDING`.

### Fetch a single investigation

```http
GET /investigations/{investigation_id}
```

Returns an investigation record with evidence, tool history, and draft verdict.

### Record a human decision

```http
POST /investigations/{investigation_id}/decision
```

Request body:

```json
{
  "decision": "APPROVE",
  "reviewed_by": "Analyst Name",
  "final_verdict": "DUPLICATE",
  "override_reason": null
}
```

Allowed decisions:

- `APPROVE`
- `REJECT`
- `OVERRIDE`

Allowed final verdict values:

- `DUPLICATE`
- `NOT_DUPLICATE`
- `UNSURE`

### View the audit log

```http
GET /audit
```

Returns all investigations with tool history, evidence, and human decisions.

## How the flow works

### Candidate generation

`app/candidate_generator.py` creates raw candidate pairs using:

- same `contact_email`
- fuzzy `account_name` matches
- shared subject tokens

This is intentionally high-recall and deterministic.

### Candidate scoring

`app/candidate_ranker.py` computes a combined score using:

- same email
- fuzzy account similarity
- fuzzy subject similarity
- subject token overlap

It buckets results into `HIGH`, `LOW`, or `DISCARD`.

### Agent investigation

`app/agent.py` does the core investigation:

- starts with agent state and tool history
- asks Gemini which tool(s) to run next
- executes deterministic Python tools from `app/tools.py`
- collects evidence in structured form
- enforces a bounded loop
- generates a structured final verdict
- returns `DUPLICATE`, `NOT_DUPLICATE`, or `UNSURE` with confidence

### Why these tools?

The selected tools capture complementary evidence:

- `compare_fields` validates exact structured CRM fields such as email, account, channel, and status.
- `fuzzy_score` detects approximate textual similarity in account names, subjects, and descriptions.
- `timeline_gap` determines whether two reports occurred close enough in time to indicate a likely duplicate.

These deterministic tools provide explainable evidence while allowing the LLM to decide which tool to invoke based on the current investigation state.

### Human-in-the-loop

The backend enforces the human approval gate. Investigations remain in the `PENDING` state until a reviewer records an `APPROVE`, `REJECT`, or `OVERRIDE` decision through the API. Finalization is not possible without a recorded human decision.

## Testing the flow manually

1. Create `.env` with your `GOOGLE_API_KEY`.
2. Activate the virtual environment.
3. Run the batch investigation flow:

```bash
python -m app.main
```

4. Start the API:

```bash
uvicorn app.api:app --reload --port 8000
```

5. Visit the Swagger docs:

```text
http://127.0.0.1:8000/docs
```

6. Use `/investigations` to confirm pending cases, then `/investigations/{id}/decision` to approve/reject.

## Example curl commands

List pending investigations:

```bash
curl http://127.0.0.1:8000/investigations
```

Get a single investigation:

```bash
curl http://127.0.0.1:8000/investigations/1
```

Approve an investigation:

```bash
curl -X POST http://127.0.0.1:8000/investigations/1/decision \
  -H "Content-Type: application/json" \
  -d '{"decision":"APPROVE","reviewed_by":"Alice","final_verdict":"DUPLICATE"}'
```

## Trade-offs

- SQLite was chosen over PostgreSQL for simplicity and rapid local setup.
- Candidate generation favors recall over precision, because the agent and human reviewer filter false positives.
- Investigations are limited to the top 10 high-priority candidate pairs in the batch flow.
- No frontend is implemented; the review flow is API-first using FastAPI and Swagger.

## Known Limitations

- No authentication or authorization layer.
- No vector similarity / embeddings for deeper semantic matching.
- Single reviewer workflow only.
- Local SQLite storage is not horizontally scalable.
- The AI agent relies on a single LLM model and may be affected by rate limits.

## Future Work

- Add authentication and role-based access control (RBAC) for reviewers and administrators.
- Build a React-based review dashboard for investigating, approving, rejecting, and overriding cases.
- Support larger CRM datasets with scalable storage such as PostgreSQL and background workers.
- Integrate semantic similarity using embeddings for reworded duplicate detection.
- Introduce asynchronous/background processing for large investigation batches.
- Add Docker support and CI/CD pipelines for easier deployment.
- Explore agent frameworks such as LangGraph or LangChain for more advanced orchestration and extensibility.

## Architecture Diagram

```
CSV
  ↓
Candidate Generator
  ↓
Candidate Ranker
  ↓
AI Agent
  ↓
SQLite
  ↓
FastAPI
  ↓
Human Review
  ↓
Audit
```

## Demo Flow

1. Run batch investigation:

```bash
python -m app.main
```

2. Start the API:

```bash
uvicorn app.api:app --reload --port 8000
```

3. Open Swagger UI:

```text
http://127.0.0.1:8000/docs
```

4. Call API endpoints:

- `GET /investigations`
- `GET /investigations/{id}`
- `POST /investigations/{id}/decision`
- `GET /audit`

## Notes

- This project expects a valid Google Gemini API key.
- The API server and batch runner are separate flows; run `app.main` to seed investigations before reviewing them in the API.
- Audit history is stored in `crm_agent.db` and returned by `/audit`.

## AI Assistant Disclosure

AI coding assistants (ChatGPT and GitHub Copilot) were used for brainstorming, implementation assistance, debugging, and documentation. All generated code and documentation were manually reviewed, tested, and understood before submission.

