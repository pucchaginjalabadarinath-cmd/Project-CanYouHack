# Handoff - LL suffering

> Updated 2026-09-12T16:41:19+00:00 by 25bcs270 (session 0912-1640, track 2)
> Read this first. The full log is cyhi-logs/session.md.

## Project
DSA Assignment Portal with Plagiarism/AI-use Detection
Team: LL suffering | Track 2 (Campus) | Can You Hack It? — free-tier only, ~20hr budget

## What the product does
1. Professor creates an Assignment, uploads its PDF, adds Questions under it
   (each question = one upload slot). Professor also uploads ONE pure-AI-generated
   reference solution per question (not shown to students).
2. Students log in, see assignments, upload their C/C++ code submission per
   question before the deadline.
3. After the deadline, professor/TA triggers a batch analysis job which runs
   BOTH models over all submissions for that question:
     a) Similarity model  -> pairwise similarity between every student pair,
        AND similarity between each student and the professor's AI reference.
     b) Perplexity model  -> avg + variance of per-line perplexity for each
        student's file (blank lines excluded), z-scored against the class
        distribution for that question and against the AI reference's own
        stats (calibration anchor).
4. A weighted flag_score combines: peer_similarity, ai_reference_similarity,
   perplexity_signal. Anyone above threshold is flagged.
5. Professor + TAs see a Flagged Students dashboard: % weight contributed by
   each model, the name of the peer they matched highest with (for TAs to
   cross-check, e.g. on WhatsApp), and a side-by-side diff view.

## Models (only two — confirmed, do not add a third)
1. SIMILARITY — `copydetect` (pip, MIT-licensed, winnowing/k-gram
   fingerprinting, MOSS/JPlag family). Runs locally in the backend, no
   hosting needed. Two comparisons per question: student-vs-student (all
   pairs) and student-vs-AI-reference.
2. PERPLEXITY — `NinedayWang/PolyCoder-160M` on Hugging Face (GPT-NeoX,
   160M params, requires `transformers>=4.23.0`). Trained on C/C++ among 12
   languages, confirmed match since the course is C/C++ only. Hosted on the
   team's HF Space `DSA-Cheating-Detector` (Gradio SDK — see "Resources"
   below), called via `gradio_client`, NOT loaded in the main backend
   (~700MB won't fit Render's free ~512MB RAM). Full reference
   implementation in `POLYCODER_GUIDE.md`.

## Flag scoring formula
flag_score = w1*peer_similarity + w2*ai_reference_similarity + w3*perplexity_signal
Starting weights: 0.4 / 0.35 / 0.25 — tune after first real run. Store each
weighted component separately so the dashboard can show "which model
contributed what %" per flagged student.

## Resources — REAL account state as of 2026-09-12
- Supabase project created: URL `https://momnewqsvslzjmmwyyvw.supabase.co`,
  publishable key in `frontend/.env` and known to the team. Still needed:
  DB password (for `DATABASE_URL`) and secret key (for
  `SUPABASE_SECRET_KEY`, only needed once storage.py/#5 is built).
- Hugging Face Space created: `DSA-Cheating-Detector` (Gradio SDK, CPU
  Basic, free). Files to push are ready in `hf-space/` in this repo — NOT
  yet pushed to the Space's own git remote. Space's public/private status
  not yet confirmed (affects whether `gradio_client` needs a token).
- GitHub / Vercel / Render accounts: not yet confirmed set up.
- College email domain confirmed: `iiitdmj.ac.in` — already in
  `frontend/.env` as `VITE_COLLEGE_EMAIL_DOMAIN`.
- Full free-tier details in `RESOURCES.md`; 150-student capacity math
  already done there — no sharding needed.

## IMPORTANT — auth.py was corrected this session
Original `auth.py` verified Supabase JWTs against a static
`SUPABASE_JWT_SECRET` (legacy HS256 shared-secret approach). This was
changed to fetch the project's JWKS (`SUPABASE_URL + /auth/v1/.well-known/
jwks.json`) via `PyJWKClient` instead, because: (1) the team's Supabase key
is in the new `sb_publishable_...` format, meaning the project is on
Supabase's new key system, and (2) per Supabase's own docs, projects
created since Nov 2025 often don't expose a legacy JWT secret at all. The
JWKS approach works for both legacy and new signing methods and needs no
secret to copy into `.env` — `SUPABASE_JWT_SECRET` has been REMOVED from
`.env.example`, don't reintroduce it. `pyjwt[crypto]` (not plain `pyjwt`)
is required in `requirements.txt` for this to work (ES256/RS256 support).

## Current build status (file-by-file)
DONE / working (backend): models.py, db.py, auth.py (JWKS version), main.py,
  routers/auth.py
DONE / working (frontend): supabaseClient.js, client.js (auth endpoints
  only), Login.jsx, Signup.jsx (handles Confirm-email on/off), RoleGuard.jsx,
  Navbar.jsx, App.jsx (routing + auth)
PREPPED, NOT YET PUSHED: hf-space/app.py, requirements.txt, README.md —
  ready to push to the Space's git remote, not done yet
STILL EMPTY STUBS (backend): schemas.py, storage.py, routers/assignments.py,
  routers/submissions.py, routers/flags.py, services/similarity_service.py,
  services/perplexity_service.py, services/flag_scoring.py, scripts/run_analysis.py
STILL EMPTY STUBS (frontend): ProfessorDashboard.jsx, AssignmentCreate.jsx,
  QuestionDetail.jsx, SubmissionUpload.jsx, StudentDashboard.jsx,
  FlaggedStudents.jsx, DiffViewer.jsx, FileUploader.jsx, ScoreBadge.jsx
NOT YET TESTED: nothing has run against the real Supabase project yet (DB
  password still missing, so DATABASE_URL is a placeholder) or the real HF
  Space (files not pushed yet).

## Repo/docs map
- `HANDOFF.md` (this file) — state + context, read first every session
- `ISSUES.md` — 23 issues; #14, #15 DONE; #22, #23 IN PROGRESS; rest open
- `FILE_WORKING_GUIDE.md` — build order + how to approach each empty file
- `RESOURCES.md` — free accounts/models/libraries, Confirm-email note,
  RAM-split rationale
- `POLYCODER_GUIDE.md` — canonical PolyCoder implementation, Steps 6-7
  updated to match the real Gradio Space + gradio_client
- `hf-space/` — files to push into the HF Space's own git repo (separate
  remote from this one)
- `cyhi-logs/` — turn-by-turn history (`cyhi-logs/bin/cyhi status`)

## Next 3 things
1. Get the Supabase DB password and secret key, fill `backend/.env` for
   real, run the backend locally against the real project.
2. Push `hf-space/`'s 3 files into the Space's git remote, confirm it
   builds (check the Space's Logs tab), test calling it with `gradio_client`
   from a scratch script before wiring into `perplexity_service.py`.
3. Backend-first per `FILE_WORKING_GUIDE.md`: `schemas.py` next (mechanical
   from `models.py`), then `storage.py`, then the assignments/submissions
   routers.

## Decisions (and why) — consolidated, chronological
- Dropped a third "watermark detection" model early — only 2 models:
  similarity + perplexity.
- Dropped boilerplate-exclusion — professor gives no starter code.
- Self-hosted PolyCoder over any commercial API — hard constraint, need raw
  logprobs, no free-tier chat API exposes them.
- Switched codegen-350M-multi -> PolyCoder-160M once C/C++-only confirmed.
- Chose Supabase over hand-rolled auth/DB/storage to save setup hours.
- Batch job runs only after deadline, never live per-submission — O(n^2).
- Confirmed 150 students needs no DB/storage sharding.
- Split `get_current_user` from `decode_supabase_token` to handle the
  post-signup, pre-profile-row moment in `POST /auth/profile`.
- Added sessionStorage stash-and-resume in Login/Signup for Supabase's
  default "Confirm email" setting.
- Switched `auth.py` from static JWT secret to JWKS verification — see
  "IMPORTANT" section above, this is a correctness fix tied to real
  Supabase account behavior, not a style preference.
- HF Space came out as Gradio SDK (not Docker+FastAPI as first sketched) —
  adapted `hf-space/app.py` and the backend's calling convention
  (`gradio_client` instead of raw `requests`) to match reality rather than
  fighting the template.

## Don't retry
- Don't get token-level logprobs from commercial chat APIs for perplexity.
- Don't build a custom fingerprinting algorithm — `copydetect` does this.
- Don't run the analysis pipeline synchronously in a request handler.
- Don't reintroduce Flask/session-cookie auth — team decided Supabase.
- Don't create a second `models.py` or separate auth config file.
- Don't remove the sessionStorage stash-and-resume logic in Login/Signup.
- Don't shard student data across groups — checked at 150 students, not needed.
- Don't reintroduce `SUPABASE_JWT_SECRET` / static-secret JWT verification —
  removed on purpose, JWKS is the correct approach now (see IMPORTANT above).
- Don't rewrite `hf-space/app.py` as Docker+FastAPI — the Space is Gradio
  SDK already, work with that, not against it.
