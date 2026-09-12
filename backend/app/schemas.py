"""
Pydantic request/response schemas mirroring models.py.

Per ISSUES.md #3: every router below imports its request/response types
from HERE, not ad-hoc dicts. (routers/auth.py predates this file and
defines its own small BaseModels inline - leave that working code alone
per FILE_WORKING_GUIDE.md, but any NEW router - assignments, submissions,
flags - must import from here.)
"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr

from .models import RoleEnum as _RoleEnum, FlagStatusEnum as _FlagStatusEnum

# Pydantic v2 wants a plain Python type for validation, not a SQLAlchemy
# Enum column object - pull the literal choices out of the SQLAlchemy Enum
# so both layers stay in sync off one source of truth (models.py) instead
# of re-typing the allowed values a second time here.
Role = Literal[tuple(_RoleEnum.enums)]  # "professor" | "ta" | "student"
FlagStatus = Literal[tuple(_FlagStatusEnum.enums)]  # "pending" | "reviewed" | "dismissed"


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    role: Role


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: EmailStr
    role: Role
    created_at: datetime


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------


class AssignmentCreate(BaseModel):
    title: str
    pdf_url: Optional[str] = None
    deadline: datetime


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    pdf_url: Optional[str] = None
    deadline: datetime
    created_by: str


# ---------------------------------------------------------------------------
# Question
# ---------------------------------------------------------------------------


class QuestionCreate(BaseModel):
    assignment_id: str
    number: int
    description: str
    # Not shown to students - only professor-facing routes should ever
    # populate/return this. Optional at creation since the reference-
    # solution upload may happen as a separate follow-up call.
    ai_reference_url: Optional[str] = None


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assignment_id: str
    number: int
    description: str
    ai_reference_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------


class SubmissionCreate(BaseModel):
    question_id: str
    language: str  # "c" | "cpp" per HANDOFF.md scope
    file_url: str


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question_id: str
    student_id: str
    file_url: str
    language: str
    submitted_at: datetime


# ---------------------------------------------------------------------------
# FlagSummary (per-model weight breakdown, for FlaggedStudents.jsx)
# ---------------------------------------------------------------------------


class FlagSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_id: str
    question_id: str
    total_score: float
    # Per-model weight breakdown - required so the frontend can render the
    # "which model contributed what %" panel described in HANDOFF.md.
    peer_weight_pct: float
    ai_ref_weight_pct: float
    perplexity_weight_pct: float
    top_matched_peer_id: Optional[str] = None
    status: FlagStatus


# ---------------------------------------------------------------------------
# Detection model outputs - not explicitly listed in ISSUES.md #3 but
# needed by the flags router / DiffViewer.jsx. Kept here rather than as
# ad-hoc dicts, consistent with "schemas live in schemas.py".
# ---------------------------------------------------------------------------


class SimilarityPairOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question_id: str
    student_a_id: str
    student_b_id: str
    score: float
    match_regions_json: Optional[Any] = None


class AiSimilarityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question_id: str
    student_id: str
    score: float
    match_regions_json: Optional[Any] = None


class PerplexityScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    submission_id: str
    avg_ppl: float
    variance_ppl: float
    zscore_avg: float
    zscore_variance: float
