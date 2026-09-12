"""
Assignments/Questions router. Per ISSUES.md #6.

Endpoints:
  POST /assignments                        professor/ta only - create + PDF upload
  GET  /assignments                        any logged-in role - role-aware list
  POST /assignments/{id}/questions         professor/ta only - add question + AI ref upload
  GET  /assignments/{id}/questions         any logged-in role - role-aware list

Uploads are multipart/form-data (title/deadline/etc as Form fields, files
as UploadFile) rather than JSON bodies, since both endpoints that create
things also take a file. `storage.py` (ISSUES.md #5) does the actual
upload; this file only decides *whether* a file is present and *where* it
goes (bucket/path naming), per FILE_WORKING_GUIDE.md's "keep storage.py a
thin I/O layer, business logic lives in the router" rule.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import schemas, storage
from ..auth import get_current_user, require_role
from ..db import get_db
from ..models import Assignment, Question, User

router = APIRouter(prefix="/assignments", tags=["assignments"])

PDF_BUCKET = "assignment-pdfs"
AI_REFERENCE_BUCKET = "ai-references"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _get_assignment_or_404(db: Session, assignment_id: str) -> Assignment:
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="assignment not found")
    return assignment


def _ensure_assignment_visible(assignment: Assignment, user: User) -> None:
    """
    Students can't see draft assignments at all (not just their questions) -
    a direct GET on a known draft assignment's id should 404 for a student,
    same as if it didn't exist, rather than leaking that a draft exists.
    """
    if user.role == "student" and assignment.is_draft:
        raise HTTPException(status_code=404, detail="assignment not found")


def _question_out_for(question: Question, user: User) -> dict:
    """
    Builds the response dict for one question, per-role. Per ISSUES.md #6's
    acceptance criteria ("the AI reference file URL is never included in
    responses served to role=student") this OMITS the key entirely for
    students rather than nulling it out, so there's nothing to leak even
    by inspecting response shape.
    """
    out = schemas.QuestionOut.model_validate(question).model_dump()
    if user.role == "student":
        out.pop("ai_reference_url", None)
    return out


# ---------------------------------------------------------------------------
# POST /assignments
# ---------------------------------------------------------------------------


@router.post("", response_model=schemas.AssignmentOut)
def create_assignment(
    title: str = Form(...),
    deadline: datetime = Form(...),
    is_draft: bool = Form(False),
    pdf: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("professor", "ta")),
):
    """
    require_role("professor", "ta") means a student token gets a 403 here
    before any of this code runs - satisfies ISSUES.md #6's "a student
    token cannot create an assignment" acceptance criterion.
    """
    assignment = Assignment(
        title=title,
        deadline=deadline,
        is_draft=is_draft,
        created_by=user.id,
    )
    # Flush first so `assignment.id` exists (server-generated UUID default)
    # to use as the storage path, without committing a half-built row yet.
    db.add(assignment)
    db.flush()

    if pdf is not None:
        pdf_bytes = pdf.file.read()
        assignment.pdf_url = storage.upload_file(
            PDF_BUCKET, f"{assignment.id}/{pdf.filename}", pdf_bytes
        )

    db.commit()
    db.refresh(assignment)
    return assignment


# ---------------------------------------------------------------------------
# GET /assignments
# ---------------------------------------------------------------------------


@router.get("", response_model=List[schemas.AssignmentOut])
def list_assignments(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Any logged-in role can list - professors/TAs see everything (including
    drafts, so they can keep working on them), students only see
    non-draft ones. This is the "role-aware" list from ISSUES.md #6.
    """
    query = db.query(Assignment)
    if user.role == "student":
        query = query.filter(Assignment.is_draft.is_(False))
    return query.order_by(Assignment.deadline).all()


# ---------------------------------------------------------------------------
# POST /assignments/{id}/questions
# ---------------------------------------------------------------------------


@router.post("/{assignment_id}/questions")
def create_question(
    assignment_id: str,
    number: int = Form(...),
    description: str = Form(...),
    ai_reference_solution: Optional[UploadFile] = File(
        None,
        description="Professor's pure-AI-generated reference solution. Never shown to students.",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("professor", "ta")),
):
    assignment = _get_assignment_or_404(db, assignment_id)

    question = Question(
        assignment_id=assignment.id,
        number=number,
        description=description,
    )
    db.add(question)
    db.flush()

    if ai_reference_solution is not None:
        ref_bytes = ai_reference_solution.file.read()
        question.ai_reference_url = storage.upload_file(
            AI_REFERENCE_BUCKET,
            f"{assignment.id}/{question.id}/{ai_reference_solution.filename}",
            ref_bytes,
        )

    db.commit()
    db.refresh(question)

    # Uses the same per-role redaction as the GET list below - the
    # professor/TA who just uploaded the reference gets to see the URL
    # back in the create response too, since require_role already
    # guarantees only staff can reach this endpoint.
    return _question_out_for(question, user)


# ---------------------------------------------------------------------------
# GET /assignments/{id}/questions
# ---------------------------------------------------------------------------


@router.get("/{assignment_id}/questions")
def list_questions(
    assignment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assignment = _get_assignment_or_404(db, assignment_id)
    _ensure_assignment_visible(assignment, user)

    questions = (
        db.query(Question)
        .filter(Question.assignment_id == assignment_id)
        .order_by(Question.number)
        .all()
    )
    return [_question_out_for(q, user) for q in questions]
