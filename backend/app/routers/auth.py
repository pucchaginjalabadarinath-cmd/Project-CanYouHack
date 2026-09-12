"""
Auth router. Per ISSUES.md #4: since we're using Supabase Auth, signup and
login themselves happen FRONTEND -> SUPABASE DIRECTLY (see
frontend/src/pages/Login.jsx, Signup.jsx) - this backend never handles
passwords. The two things the backend still must do:

1. POST /auth/profile - right after Supabase signup succeeds on the
   frontend, it calls this ONCE to register the new user's name + role in
   OUR users table (Supabase itself has no concept of "professor" vs
   "student" - that's our field, not theirs).
2. GET /auth/me - lets any logged-in page ask "who am I / what's my role"
   using just the JWT, so the frontend can decide what to render
   (see RoleGuard.jsx, Navbar.jsx).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user, decode_supabase_token
from ..db import get_db
from ..models import User

router = APIRouter(prefix="/auth", tags=["auth"])

VALID_ROLES = {"student", "ta", "professor"}


class ProfileOut(BaseModel):
    id: str
    name: str
    email: str
    role: str

    class Config:
        from_attributes = True


class CreateProfileIn(BaseModel):
    name: str
    role: str  # "student" | "ta" | "professor"


@router.get("/me", response_model=ProfileOut)
def get_me(user: User = Depends(get_current_user)):
    """
    Returns the logged-in user's profile (name, email, role). The frontend
    calls this right after login to decide which dashboard to redirect to.
    """
    return user


@router.post("/profile", response_model=ProfileOut)
def create_profile(
    body: CreateProfileIn,
    claims: dict = Depends(decode_supabase_token),
    db: Session = Depends(get_db),
):
    """
    Called ONCE by the frontend immediately after a successful Supabase
    signup. Uses `decode_supabase_token` (not `get_current_user`) on purpose
    - at this exact moment the token is valid but no profile row exists yet,
    so requiring one would be a chicken-and-egg 404.
    """
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {sorted(VALID_ROLES)}")

    supabase_user_id = claims.get("sub")
    email = claims.get("email")
    if not supabase_user_id or not email:
        raise HTTPException(status_code=401, detail="token missing required claims")

    existing = db.query(User).filter(User.id == supabase_user_id).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="profile already exists for this account")

    user = User(id=supabase_user_id, name=body.name, email=email, role=body.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
