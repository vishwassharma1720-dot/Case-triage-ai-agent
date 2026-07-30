from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Literal


from app.database import (
    get_pending_investigations,
    get_investigation,
    record_human_decision,
    get_audit_log,
)

app = FastAPI(
    title="CRM Duplicate Investigation API"
)

class HumanDecision(BaseModel):
    decision: Literal[
        "APPROVE",
        "REJECT",
        "OVERRIDE"
    ]

    reviewed_by: str

    final_verdict: Literal[
        "DUPLICATE",
        "NOT_DUPLICATE",
        "UNSURE"
    ] | None = None

    override_reason: str | None = None

@app.get("/investigations")
def investigations():

    return get_pending_investigations()

@app.get("/investigations/{investigation_id}")
def investigation(investigation_id: int):

    result = get_investigation(investigation_id)

    if result is None:
        raise HTTPException(404, "Investigation not found")

    return result

@app.post("/investigations/{investigation_id}/decision")
def decision(
    investigation_id: int,
    body: HumanDecision,
):

    if get_investigation(investigation_id) is None:
        raise HTTPException(404, "Investigation not found")

    record_human_decision(
        investigation_id,
        body.decision,
        body.reviewed_by,
    )

    return {
        "message": "Decision recorded"
    }

@app.get("/audit")
def audit():

    return get_audit_log()