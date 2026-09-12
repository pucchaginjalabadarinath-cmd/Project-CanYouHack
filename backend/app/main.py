"""
FastAPI app entrypoint. Wires up routers and CORS.
Other routers (assignments, submissions, flags) get added here the same
way auth_router is - one include_router() line each, do not build a
separate wiring mechanism.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from .db import engine
from .models import Base
from .routers.auth import router as auth_router
from .routers.assignments import router as assignments_router
from .routers.submissions import router as submissions_router
from .routers.flags import router as flags_router

app = FastAPI(title="DSA Assignment Portal API")

# Creates any tables that don't exist yet. Fine for a hackathon; a real
# project would use Alembic migrations instead of this.
Base.metadata.create_all(bind=engine)

FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(assignments_router)
app.include_router(submissions_router)
app.include_router(flags_router)


@app.get("/health")
def health():
    return {"status": "ok"}
