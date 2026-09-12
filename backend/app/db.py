"""
DB engine + session, per FILE_WORKING_GUIDE.md: one engine, one SessionLocal,
one get_db() generator. Fails loudly if DATABASE_URL is missing rather than
silently defaulting - a missing env var should be obvious immediately, not
discovered as a confusing runtime error three files later.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy backend/.env.example to backend/.env "
        "and fill in your Supabase Postgres connection string (found in "
        "Supabase dashboard -> Project Settings -> Database -> Connection string)."
    )

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency - yields a DB session, always closes it after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
