"""
Submissions router. Per ISSUES.md #7.

Endpoints (student only, enforced via require_role):
  POST /questions/{id}/submissions        upload code file, reject if past deadline
  GET  /questions/{id}/submissions/me     the current student's own submission status
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import schemas, storage
from ..auth import require_role
from ..db import get_db
from ..models import Question, Submission, User

router = APIRouter(prefix="/questions", tags=["submissions"])

SUBMISSIONS_BUCKET = "submissions"

# Per HANDOFF.md scope - submissions are C/C++ only, matching
# perplexity_service.py's model choice (PolyCoder-160M was picked
# specifically because it's trained on C/C++, unlike SantaCoder).
EXTENSION_BY_LANGUAGE = {"c": ".c", "cpp": ".cpp"}


def _get_question_or_404(db: Session, question_id: str) -> Question:
    question = db.query(Question).filter(Question.id == question_id).first()
    if question is None:
        raise HTTPException(status_code=404, detail="question not found")
    return question


def _deadline_of(question: Question) -> datetime:
    # The deadline lives on the parent Assignment, not the Question itself
    # - see models.py's Assignment.deadline.
    return question.assignment.deadline


@router.post("/{question_id}/submissions", response_model=schemas.SubmissionOut)
def submit_code(
    question_id: str,
    language: str = Form(..., description="\"c\" or \"cpp\""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("student")),
):
    """
    require_role("student") means a professor/TA token gets 403 before any
    of this runs - same pattern as ISSUES.md #6's assignment-creation
    guard, just restricted to the opposite role.
    """
    question = _get_question_or_404(db, question_id)

    if language not in EXTENSION_BY_LANGUAGE:
        raise HTTPException(
            status_code=400,
            detail=f"language must be one of {sorted(EXTENSION_BY_LANGUAGE)}",
        )

    now = datetime.now(timezone.utc)
    deadline = _deadline_of(question)
    if now > deadline:
        # ISSUES.md #7 acceptance criterion: submitting after the deadline
        # returns 400 (a "too late" problem, not a permissions problem -
        # kept distinct from the 403s require_role() raises).
        raise HTTPException(
            status_code=400,
            detail=(
                f"deadline for this question was {deadline.isoformat()} "
                "- submission window is closed"
            ),
        )

    file_bytes = file.file.read()

    existing = (
        db.query(Submission)
        .filter(Submission.question_id == question_id, Submission.student_id == user.id)
        .first()
    )

    # Same storage path every time for this (question, student) pair -
    # keyed by language's extension rather than the uploaded filename, so a
    # re-submission genuinely overwrites the previous file in storage too
    # (not just the DB row), even if the student renamed the file locally.
    # storage.py's Supabase backend uploads with x-upsert=true and the
    # local-disk backend overwrites-by-default - both rely on this path
    # being identical across submissions to satisfy ISSUES.md #7's
    # "re-submitting before the deadline overwrites the previous file".
    storage_path = f"{question_id}/{user.id}/submission{EXTENSION_BY_LANGUAGE[language]}"
    file_url = storage.upload_file(SUBMISSIONS_BUCKET, storage_path, file_bytes)

    if existing is not None:
        existing.file_url = file_url
        existing.language = language
        existing.submitted_at = now
        submission = existing
    else:
        submission = Submission(
            question_id=question_id,
            student_id=user.id,
            file_url=file_url,
            language=language,
            submitted_at=now,
        )
        db.add(submission)

    db.commit()
    db.refresh(submission)
    return submission


@router.get("/{question_id}/submissions/me", response_model=schemas.SubmissionOut)
def get_my_submission(
    question_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("student")),
):
    _get_question_or_404(db, question_id)

    submission = (
        db.query(Submission)
        .filter(Submission.question_id == question_id, Submission.student_id == user.id)
        .first()
    )
    if submission is None:
        raise HTTPException(status_code=404, detail="no submission yet for this question")
    return submission
