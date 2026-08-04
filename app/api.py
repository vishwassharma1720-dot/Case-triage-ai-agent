import os
import shutil
import tempfile

import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from typing import Literal
from fastapi.middleware.cors import CORSMiddleware


from app.database import (
    get_pending_investigations,
    get_investigation,
    record_human_decision,
    get_audit_log,
)
from app.service import run_investigation_pipeline

app = FastAPI(
    title="CRM Duplicate Investigation API"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

@app.post("/process-csv")
def process_csv(file: UploadFile | None = File(None)):
    if file is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file is required.",
        )

    allowed_types = {"text/csv", "application/csv", "application/vnd.ms-excel"}
    if not (
        file.filename.lower().endswith(".csv")
        or file.content_type in allowed_types
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a CSV.",
        )

    tmp_file = None
    try:
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
        shutil.copyfileobj(file.file, tmp_file)
        tmp_file.close()

        result = run_investigation_pipeline(tmp_file.name)

        return {
            "message": "Processing completed",
            "processed_pairs": result["processed_pairs"],
            "pending_reviews": result["pending_reviews"],
        }
    except pd.errors.EmptyDataError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded CSV is empty.",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {exc}",
        )
    finally:
        if tmp_file is not None:
            try:
                os.remove(tmp_file.name)
            except OSError:
                pass


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
        body.final_verdict,
        body.override_reason,
    )

    return {
        "message": "Decision recorded"
    }

@app.get("/audit")
def audit():

    return get_audit_log()