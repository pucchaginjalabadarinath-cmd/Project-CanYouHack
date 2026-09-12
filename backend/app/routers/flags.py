"""
Flags router. Per ISSUES.md #11.

Endpoints (all professor/TA only, via require_role):
  POST  /questions/{id}/run-analysis  - kicks off scripts/run_analysis.py's
                                         logic (#12) in the background and
                                         returns 202 immediately.
  GET   /questions/{id}/flags         - list FlagSummary rows for the
                                         question, sorted by total_score
                                         desc.
  PATCH /flags/{id}                   - mark a flag reviewed/dismissed.
"""

from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import schemas
from ..auth import require_role
from ..db import SessionLocal, get_db
from ..models import FlagSummary, Question, User

router = APIRouter(tags=["flags"])


def _run_analysis_in_background(question_id: str) -> None:
    """
    Runs on FastAPI's background-task thread, so it needs its OWN DB
    session - the request-scoped session from `get_db()` is closed the
    moment the endpoint below returns its 202, well before this actually
    executes.

    `scripts.run_analysis` is imported here (inside the function), not at
    module import time, so that a bug in the analysis script can't prevent
    THIS router - and therefore GET /flags and PATCH /flags/{id} - from
    loading at all. This is an absolute import deliberately: `scripts/`
    and `app/` are sibling top-level directories under backend/, not
    nested packages of each other, so a relative import here
    (e.g. `from ...scripts...`) cannot work regardless of how many dots
    are used - it must be `from scripts...`.
    """
    from scripts.run_analysis import run_analysis

    db = SessionLocal()
    try:
        run_analysis(question_id, db)
    finally:
        db.close()


@router.post("/questions/{question_id}/run-analysis", status_code=202)
def trigger_run_analysis(
    question_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("professor", "ta")),
):
    """
    Per ISSUES.md #11's acceptance criteria: this returns immediately
    (202) while the actual analysis runs in the background via FastAPI's
    BackgroundTasks - the request is never blocked waiting for
    copydetect/perplexity to finish. `GET /questions/{id}/flags` reflects
    the results once the background job commits them.
    """
    question = db.query(Question).filter(Question.id == question_id).first()
    if question is None:
        raise HTTPException(status_code=404, detail="question not found")

    background_tasks.add_task(_run_analysis_in_background, question_id)
    return {"message": "analysis started", "question_id": question_id}


@router.get("/questions/{question_id}/flags", response_model=List[schemas.FlagSummaryOut])
def list_flags(
    question_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("professor", "ta")),
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if question is None:
        raise HTTPException(status_code=404, detail="question not found")

    return (
        db.query(FlagSummary)
        .filter(FlagSummary.question_id == question_id)
        .order_by(FlagSummary.total_score.desc())
        .all()
    )


class UpdateFlagStatusIn(BaseModel):
    status: schemas.FlagStatus


@router.patch("/flags/{flag_id}", response_model=schemas.FlagSummaryOut)
def update_flag_status(
    flag_id: str,
    body: UpdateFlagStatusIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("professor", "ta")),
):
    """Marks a flag reviewed/dismissed (or back to pending)."""
    flag = db.query(FlagSummary).filter(FlagSummary.id == flag_id).first()
    if flag is None:
        raise HTTPException(status_code=404, detail="flag not found")

    flag.status = body.status
    db.commit()
    db.refresh(flag)
    return flag
