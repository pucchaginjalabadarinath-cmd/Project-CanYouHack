# GitHub Issues — LL suffering / DSA Portal

Copy each block below into a GitHub issue (title = the `##` heading). Suggested
labels are in `[brackets]`. Ordered roughly in the sequence you should tackle
them — earlier issues unblock later ones.

---

## 1. Backend: DB models (`backend/app/models.py`) `[backend, blocker]`

**File:** `backend/app/models.py`

Define SQLAlchemy models for:
- `User` — id, name, email, role (enum: professor/ta/student), created_at
- `Assignment` — id, title, pdf_url, deadline, created_by (FK User)
- `Question` — id, assignment_id (FK), number, description, ai_reference_url
- `Submission` — id, question_id (FK), student_id (FK User), file_url, language, submitted_at
- `SimilarityPair` — id, question_id (FK), student_a_id, student_b_id, score, match_regions_json
- `AiSimilarity` — id, question_id (FK), student_id (FK), score, match_regions_json
- `PerplexityScore` — id, submission_id (FK), avg_ppl, variance_ppl, zscore_avg, zscore_variance
- `FlagSummary` — id, student_id (FK), question_id (FK), total_score, peer_weight_pct, ai_ref_weight_pct, perplexity_weight_pct, top_matched_peer_id, status (enum: pending/reviewed/dismissed)

**Acceptance criteria:** all tables created via Alembic migration or `Base.metadata.create_all()`, foreign keys enforced, enums used for `role` and `status`.

---

## 2. Backend: DB connection (`backend/app/db.py`) `[backend, blocker]`

**File:** `backend/app/db.py`

Set up SQLAlchemy engine + session using `DATABASE_URL` from env (Supabase Postgres connection string). Export a `get_db()` FastAPI dependency that yields a session and closes it after the request.

**Acceptance criteria:** `from app.db import get_db` works in a router without circular imports; connecting to a real Supabase Postgres instance succeeds.

---

## 3. Backend: Pydantic schemas (`backend/app/schemas.py`) `[backend]`

**File:** `backend/app/schemas.py`

Request/response schemas mirroring `models.py`: `UserCreate`, `UserOut`, `AssignmentCreate`, `AssignmentOut`, `QuestionCreate`, `QuestionOut`, `SubmissionCreate`, `SubmissionOut`, `FlagSummaryOut` (must include the per-model weight breakdown fields so the frontend can render them).

**Acceptance criteria:** every router below imports its request/response types from here, not ad-hoc dicts.

---

## 4. Backend: Auth (`backend/app/auth.py`, `backend/app/routers/auth.py`) `[backend, auth, blocker]`

**Files:** `backend/app/auth.py`, `backend/app/routers/auth.py`

If using **Supabase Auth** (recommended): `auth.py` verifies the Supabase JWT sent in the `Authorization` header and extracts `user_id` + `role`; provide a `require_role(*roles)` FastAPI dependency for route protection. `routers/auth.py` only needs a `/me` endpoint returning the current user's profile row.

If hand-rolling instead: `auth.py` does password hashing (bcrypt) + JWT issue/verify; `routers/auth.py` gets `/signup` (restrict to college email domain) and `/login`.

**Acceptance criteria:** a route decorated with `require_role("professor")` returns 403 for a student token, 200 for a professor token.

---

## 5. Backend: File storage (`backend/app/storage.py`) `[backend]`

**File:** `backend/app/storage.py`

Wrapper around Supabase Storage (or local disk fallback) with two functions: `upload_file(bucket, path, file_bytes) -> url` and `download_file(url) -> bytes`. Used by both the assignment-PDF upload and the student submission upload.

**Acceptance criteria:** uploading a small `.txt` file returns a URL that `download_file` can read back byte-identical.

---

## 6. Backend: Assignments/Questions router (`backend/app/routers/assignments.py`) `[backend]`

**File:** `backend/app/routers/assignments.py`

Endpoints (professor/TA only, via `require_role`):
- `POST /assignments` — create assignment (title, deadline) + PDF upload
- `GET /assignments` — list (role-aware: students see only non-draft ones)
- `POST /assignments/{id}/questions` — add a question with its AI reference solution upload
- `GET /assignments/{id}/questions` — list questions for an assignment

**Acceptance criteria:** a student token cannot create an assignment; the AI reference file URL is never included in responses served to `role=student`.

---

## 7. Backend: Submissions router (`backend/app/routers/submissions.py`) `[backend]`

**File:** `backend/app/routers/submissions.py`

Endpoints (student only):
- `POST /questions/{id}/submissions` — upload code file, reject if `now() > deadline`
- `GET /questions/{id}/submissions/me` — student's own submission status

**Acceptance criteria:** submitting after the deadline returns 400; re-submitting before the deadline overwrites the previous file.

---

## 8. Backend: Similarity service (`backend/app/services/similarity_service.py`) `[backend, models, core]`

**File:** `backend/app/services/similarity_service.py`

Wraps `copydetect` (pip install). Two functions:
- `compare_all_students(file_paths: dict[student_id, path]) -> list[SimilarityPair rows]`
- `compare_to_reference(file_paths: dict[student_id, path], reference_path) -> list[AiSimilarity rows]`

Both must return the similarity score (0–1) AND the matched line-range data needed for the diff viewer, not just a number.

**Acceptance criteria:** running on two identical files returns ~1.0; two unrelated files return a low score; matched regions are non-empty for the identical-file case.

---

## 9. Backend: Perplexity service (`backend/app/services/perplexity_service.py`) `[backend, models, core]`

**File:** `backend/app/services/perplexity_service.py`

Load `NinedayWang/PolyCoder-160M` via `transformers` (pin `transformers>=4.23.0`
in requirements.txt — the model card requires it) once at module import (not
per-call). This is a GPT-NeoX architecture model, so load it with
`AutoModelForCausalLM` / `AutoTokenizer` same as any causal LM — no special
handling needed. Provide:
- `line_perplexity(line: str) -> float | None`
- `file_stats(filepath: str) -> {avg, variance, n_lines}` (skip blank lines)
- `zscore_against_class(student_stats, all_class_stats) -> {zscore_avg, zscore_variance}`

Since submissions are confirmed C/C++ only, you do NOT need any
language-detection or multi-language branching logic here — one model,
one code path.

**IMPORTANT — this function should call the HF Space endpoint (see issue
#22), not load the model in-process**, unless you're running it standalone
for local testing. In production it's `requests.post(HF_SPACE_URL, ...)`.

**Acceptance criteria:** running on a real ~50-line C/C++ file completes in
under ~5 seconds on CPU; blank lines are confirmed excluded by a unit test;
a file with obviously copy-pasted, uniformly-formatted AI output scores
noticeably lower avg-perplexity than a scrappy human first-attempt file
(sanity check with 2-3 real samples before considering this done).

---

## 10. Backend: Flag scoring (`backend/app/services/flag_scoring.py`) `[backend, models, core]`

**File:** `backend/app/services/flag_scoring.py`

Combine similarity + perplexity outputs per student per question into `flag_score = w1*peer_similarity + w2*ai_reference_similarity + w3*perplexity_signal` (default weights 0.4/0.35/0.25 — expose as constants at the top of the file, not magic numbers inline). Write `FlagSummary` rows including each weighted component's % contribution and the `top_matched_peer_id`.

**Acceptance criteria:** for a student who is only flagged by perplexity, `peer_weight_pct` ≈ 0; weights sum to 100% of whatever `total_score` is composed from.

---

## 11. Backend: Flags router (`backend/app/routers/flags.py`) `[backend]`

**File:** `backend/app/routers/flags.py`

Endpoints (professor/TA only):
- `POST /questions/{id}/run-analysis` — triggers `scripts/run_analysis.py` logic for that question (async/background task, must not block the request)
- `GET /questions/{id}/flags` — list flagged students sorted by `total_score` desc
- `PATCH /flags/{id}` — mark reviewed/dismissed

**Acceptance criteria:** `run-analysis` returns immediately (202-style) while the job runs in the background; `GET /flags` reflects results once the job finishes.

---

## 12. Backend: Batch analysis script (`backend/scripts/run_analysis.py`) `[backend, models]`

**File:** `backend/scripts/run_analysis.py`

Entry point that, given a `question_id`: pulls all submissions + the AI reference, runs `similarity_service` and `perplexity_service`, calls `flag_scoring`, and commits `FlagSummary` rows. Must be runnable standalone (`python scripts/run_analysis.py --question-id 3`) for local testing, and importable as a function for the background-task route in issue #11.

**Acceptance criteria:** running it twice on the same question is idempotent (doesn't duplicate rows — upsert or delete-then-insert).

---

## 13. Backend: FastAPI app entrypoint (`backend/app/main.py`) `[backend, blocker]`

**File:** `backend/app/main.py`

Creates the FastAPI app, registers all routers from `app/routers/`, sets up CORS (allow the Vercel frontend origin), and a `/health` endpoint.

**Acceptance criteria:** `uvicorn app.main:app` boots without import errors once issues #1–#12 exist (even as stubs).

---

## 14. Frontend: Auth pages (`Login.jsx`, `Signup.jsx`) `[frontend, auth]`

**Files:** `frontend/src/pages/Login.jsx`, `frontend/src/pages/Signup.jsx`

Login/signup forms wired to Supabase Auth (or backend `/login`/`/signup` if hand-rolled). On success, store session and redirect based on role: professor/TA → `/professor/dashboard`, student → `/student/dashboard`.

**Acceptance criteria:** signup rejects non-college email domains client-side with an inline error before hitting the network.

---

## 15. Frontend: Role guard + Navbar (`RoleGuard.jsx`, `Navbar.jsx`) `[frontend, auth]`

**Files:** `frontend/src/components/RoleGuard.jsx`, `frontend/src/components/Navbar.jsx`

`RoleGuard` wraps a route and redirects to `/login` if unauthenticated, or shows a 403 page if the logged-in role isn't in the allowed list. `Navbar` shows different links per role (professor/TA see "Flagged Students", students don't).

**Acceptance criteria:** a student navigating directly to `/professor/flags` (typed URL) is redirected, not just hidden from nav.

---

## 16. Frontend: Professor dashboard + assignment creation `[frontend]`

**Files:** `frontend/src/pages/ProfessorDashboard.jsx`, `frontend/src/pages/AssignmentCreate.jsx`

Dashboard lists existing assignments with deadline + question count. Creation page: title, deadline picker, PDF upload, then add N questions each with a description and an AI-reference-solution file upload.

**Acceptance criteria:** AI reference upload is visually marked "professor only — not shown to students" so nobody wires it into a student-facing component by mistake.

---

## 17. Frontend: Question detail + submission upload `[frontend]`

**Files:** `frontend/src/pages/QuestionDetail.jsx`, `frontend/src/pages/SubmissionUpload.jsx`, `frontend/src/components/FileUploader.jsx`

Student-facing: shows question description + PDF link, upload widget for their code file, shows submission status/timestamp, disables upload after deadline.

**Acceptance criteria:** attempting upload after the deadline shows a disabled state with the deadline time shown, not a silent failure.

---

## 18. Frontend: Flagged students dashboard `[frontend, core]`

**File:** `frontend/src/pages/FlaggedStudents.jsx`, `frontend/src/components/ScoreBadge.jsx`

List of flagged students per question, sorted by `total_score`, each row showing the `ScoreBadge` breakdown (peer % / ai-ref % / perplexity %) and the `top_matched_peer` name. Row click → diff viewer. Includes reviewed/dismissed action buttons calling `PATCH /flags/{id}`.

**Acceptance criteria:** the % breakdown per row visually sums to the badge's total (sanity-check against backend rounding).

---

## 19. Frontend: Diff viewer `[frontend, core]`

**File:** `frontend/src/pages/DiffViewer.jsx`

Side-by-side code view highlighting the matched regions returned by `similarity_service` (from issue #8's `match_regions_json`), for both student-vs-peer and student-vs-AI-reference comparisons.

**Acceptance criteria:** matched lines are visually highlighted on both sides in sync (same line ranges, not just two independent code blocks).

---

## 20. Frontend: API client (`frontend/src/api/client.js`) `[frontend, blocker]`

**File:** `frontend/src/api/client.js`

Single fetch wrapper attaching the auth token to every request, with typed helper functions per endpoint (`getAssignments()`, `uploadSubmission()`, `getFlags(questionId)`, etc.) so pages never call `fetch` directly.

**Acceptance criteria:** changing the backend base URL is a one-line env var change, not a find-and-replace across pages.

---

## 21. Deployment: Dockerfile + env files `[devops]`

**Files:** `backend/Dockerfile`, `backend/.env.example`, `frontend/.env.example`

Backend Dockerfile for Render/Railway deploy. `.env.example` files listing every required var (`DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_KEY`, `HF_MODEL_NAME`, frontend `VITE_API_BASE_URL`, etc.) with placeholder values, never real secrets.

**Acceptance criteria:** a teammate can `cp .env.example .env`, fill in real values, and run locally with no other guessing.

---

## 22. Deployment: Perplexity model host (HF Spaces) `[devops, models]`

**No repo file yet — separate HF Space repo.** Create a free Hugging Face
account + a new Space (SDK: "Docker" or "Gradio", CPU Basic tier — free, no
card required). In that Space, wrap `perplexity_service.py`'s `file_stats()`
logic (loading `NinedayWang/PolyCoder-160M`) in a tiny FastAPI app with one
endpoint: `POST /score` accepting `{code: str}`, returning
`{avg, variance, n_lines}`. Have the main backend call this over HTTP inside
`run_analysis.py` instead of loading the ~700MB model in-process — Render's
free tier (~512MB RAM) cannot hold it.

**Acceptance criteria:** the main backend's memory footprint stays under
Render's free-tier limit with the model hosted externally; a `curl POST` to
the Space's `/score` endpoint with a sample C file returns valid JSON within
~10s (HF free Spaces cold-start after inactivity, budget for that in the
batch job's timeout).

---

## 23. Resources setup checklist `[devops, blocker]`

**No file — this is a one-time account-setup issue, do it before #1.**

Create free accounts (no credit card needed for any of these) and store the
resulting keys in `.env` files (never commit them):
- [ ] GitHub — repo + free Actions minutes
- [ ] Vercel — link to GitHub repo for frontend auto-deploy
- [ ] Render — link to GitHub repo for backend auto-deploy (free web service)
- [ ] Supabase — new project, grab `DATABASE_URL`, `SUPABASE_URL`,
      `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`; create a Storage bucket
      for PDFs/submissions
- [ ] Hugging Face — account + new Space for PolyCoder hosting (issue #22)

Full details and free-tier limits for each are in `RESOURCES.md`.

**Acceptance criteria:** every teammate can run the project locally with
their own `.env` filled from `.env.example` using only these free accounts —
nobody needs a paid API key for anything in this project.
