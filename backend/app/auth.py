"""
Supabase JWT verification + role-based route protection.

How Supabase Auth fits in (read this before touching the file):

1. The FRONTEND talks to Supabase directly for signup/login (see
   frontend/src/pages/Login.jsx, Signup.jsx) - our backend never sees a
   password. Supabase hands the frontend back a JWT after login.
2. The frontend attaches that JWT to every API call as:
       Authorization: Bearer <token>
   (see frontend/src/api/client.js).
3. THIS file's job is only to verify that JWT was really issued by our
   Supabase project (not forged) and figure out which user + role it
   belongs to. We never issue tokens ourselves - Supabase does that.

Why we still need our own `users` table if Supabase already manages
accounts: Supabase's auth.users table stores login credentials, not
app-specific fields like "role". So at signup we write one row into our
own `users` table (same id as the Supabase user) holding the role. This
file reads that row after verifying the token.
"""

import os
import jwt  # pyjwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .db import get_db
from .models import User

SUPABASE_URL = os.environ.get("SUPABASE_URL")
if not SUPABASE_URL:
    raise RuntimeError(
        "SUPABASE_URL is not set. Find it in Supabase dashboard -> "
        "Project Settings -> API, and put it in backend/.env"
    )

# Supabase now signs tokens with per-project JWT Signing Keys (asymmetric
# ES256/RS256 by default for projects created since Nov 2025) rather than a
# single static shared secret - projects on the new key system often don't
# expose a legacy JWT secret at all. This fetches the project's public keys
# from its JWKS endpoint and matches each token to the right key via its
# "kid" header, so it works whether the project is on the new asymmetric
# signing keys or still has legacy HS256 - no secret to copy/paste, and
# nothing to update if the project rotates its signing keys later.
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
_jwk_client = PyJWKClient(JWKS_URL)

bearer_scheme = HTTPBearer()


def decode_supabase_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    """
    Verifies the Supabase-issued JWT signature/expiry only - does NOT touch
    our `users` table. Returns the raw claims dict (contains "sub" = the
    Supabase user's UUID, and "email").

    This exists as a separate, lower-level step because there's exactly one
    moment where a verified-but-profile-less token is valid on purpose:
    right after Supabase signup, before we've written the role row. Every
    other endpoint should use `get_current_user` below instead, which also
    requires the profile row to exist.
    """
    token = credentials.credentials
    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256", "HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token expired, please log in again")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"invalid token: {e}")


def get_current_user(
    claims: dict = Depends(decode_supabase_token),
    db: Session = Depends(get_db),
) -> User:
    """
    Verifies the token (via decode_supabase_token) AND requires a matching
    profile row in our `users` table (which has the role). This is what
    every real feature route should depend on. Raises 404 if the token is
    valid but no profile row exists yet (signup flow didn't finish).
    """
    supabase_user_id = claims.get("sub")
    if not supabase_user_id:
        raise HTTPException(status_code=401, detail="token missing subject claim")

    user = db.query(User).filter(User.id == supabase_user_id).first()
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="authenticated but no profile row found - signup may be incomplete",
        )

    return user


def require_role(*roles: str):
    """
    FastAPI dependency factory. Usage in any router file:

        from app.auth import require_role

        @router.get("/flags")
        def view_flags(user: User = Depends(require_role("professor", "ta"))):
            ...

    Acceptance criteria from ISSUES.md #4: a route using this returns 403
    for a token whose role isn't in `roles`, 200 (proceeds normally) for a
    matching role.
    """
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role '{user.role}' is not permitted here",
            )
        return user
    return dependency
