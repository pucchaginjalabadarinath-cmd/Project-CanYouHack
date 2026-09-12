# Handoff - LL suffering

> Updated 2026-09-12T13:41:29+00:00 by unknown (session 0912-1341, track 2)
> Read this first. The full log is cyhi-logs/session.md.

## Current state
Auth chain fully implemented: backend (models.py, db.py, auth.py,
routers/auth.py, main.py wired) + frontend (supabaseClient.js, client.js,
Login.jsx, Signup.jsx, RoleGuard.jsx, Navbar.jsx, App.jsx routing).
Uses Supabase Auth as decided - frontend talks to Supabase directly for
signup/login, backend verifies the JWT and stores role in its own `users`
table via POST /auth/profile.

## Works
- All backend files pass py_compile syntax checks.
- Manually traced import graph: main -> routers/auth -> auth -> db/models,
  no circular imports.
- require_role() dependency factory matches ISSUES.md #4 acceptance
  criteria (403 for wrong role, 200 for matching role) - same pattern
  verified working in an earlier hand-rolled Flask prototype before this
  Supabase port.
- Signup client-side college-email-domain rejection happens before any
  network call, per ISSUES.md #14.
- RoleGuard redirects unauthenticated users and 403s wrong roles even on
  direct URL navigation, per ISSUES.md #15.

## Broken
- Not yet run end-to-end against a real Supabase project (no network in
  the build sandbox) - user needs to create the Supabase project, fill in
  backend/.env and frontend/.env, then test signup->login->dashboard
  redirect for real.
- ProfessorDashboard/StudentDashboard are placeholders in App.jsx, not the
  real pages yet (ISSUES.md #16, #17 still open).

## Next 3 things
1. Create Supabase project, fill .env files, test signup/login end-to-end.
2. Build assignments.py + submissions.py routers (backend-first per
   FILE_WORKING_GUIDE.md build order) before their frontend pages.
3. Build storage.py (Supabase Storage wrapper) - needed by both PDF and
   submission uploads.

## Decisions (and why)
- Reused the require_role(*roles) dependency-factory pattern from an
  earlier hand-rolled Flask+session prototype, ported to FastAPI +
  Supabase JWT verification - same contract (decorator/dependency blocks
  by role), different transport (JWT bearer token vs session cookie).
- Split get_current_user (requires an existing profile row) from
  decode_supabase_token (verifies token only) specifically to handle the
  post-signup, pre-profile-row moment in POST /auth/profile without a
  chicken-and-egg 404.
- College email domain check lives client-side in Signup.jsx for instant
  feedback, per ISSUES.md #14's acceptance criteria - not enforced
  server-side yet, consider adding a backend check too before final submission.

## Don't retry
- Don't reintroduce Flask/session-cookie auth - team decided Supabase,
  confirmed in HANDOFF.md's Decisions section from the previous session.
- Don't create a second models.py or a separate auth config file - models.py
  is the single schema source of truth per FILE_WORKING_GUIDE.md.
> Updated 2026-09-12T12:36:20+00:00 by 25bcs270 (session 0912-1202, track 2)
> Read this first. The full log is cyhi-logs/session.md.

## Project
DSA Assignment Portal with Plagiarism/AI-use Detection
Team: LL suffering | Track 2 (Campus) | Can You Hack It?

## Current state
Idea + architecture finalized. No code written yet. Two detection models decided
(similarity + perplexity — watermark model dropped, NOT part of scope anymore).
Ready to start scaffolding backend, frontend, and the two model services.

## What the product does
1. Professor creates an Assignment, uploads its PDF, adds Questions under it
   (each question = one upload slot). Professor also uploads ONE pure-AI-generated
   reference solution per question (not shown to students).
2. Students log in, see assignments, upload their code submission per question
   before the deadline.
3. After the deadline, professor/TA triggers an analysis job (or it runs on a
   schedule) which runs BOTH models over all submissions for that question:
     a) Similarity model  -> pairwise similarity between every student pair,
        AND similarity between each student and the professor's AI reference.
     b) Perplexity model  -> avg + variance of per-line perplexity for each
        student's file, using a self-hosted code LM. Blank lines excluded.
        Z-scored against the class distribution for that question, and
        compared against the perplexity stats of the AI reference solution
        (calibration anchor).
4. A weighted flag_score combines: peer_similarity, ai_reference_similarity,
   perplexity_signal. Anyone above threshold is flagged.
5. Professor + TAs see a Flagged Students dashboard: for each flagged student,
   the % weight contributed by each model/signal, the name of the peer they
   matched highest with (so TAs know who to cross-check, e.g. on WhatsApp),
   and a side-by-side diff view of the matched code regions.

## Models (only two — do not add a third)
1. SIMILARITY MODEL
   - Library: `copydetect` (pip) — implements winnowing/k-gram fingerprinting,
     same family of algorithm as MOSS/JPlag. Fallback option: Dolos.
   - Two comparisons per question: student-vs-student (all pairs) and
     student-vs-AI-reference.
   - Output: score (0-1) + matched line ranges (for the diff viewer).
   - No boilerplate-exclusion step needed — sir does NOT provide boilerplate,
     so skip that filtering logic entirely (was planned earlier, now moot).

2. PERPLEXITY MODEL
   - CONFIRMED: DSA course submissions are C and C++ only (not multi-language,
     not Python) — this simplified the model choice.
   - Self-hosted, free, no API key: HuggingFace `transformers` +
     `NinedayWang/PolyCoder-160M` (GPT-NeoX architecture, autoregressive,
     160M params, ~700MB weights). Trained on 249GB of code across 12
     languages INCLUDING C and C++, which is exactly the team's use case —
     this is why PolyCoder replaces the earlier codegen-350M-multi choice.
   - Requires `transformers>=4.23.0` — pin this exact floor in requirements.txt,
     the model card explicitly calls this out.
   - Per line (blank lines skipped): perplexity = exp(cross-entropy loss) of
     that line under the model.
   - Per file: avg + variance (== "burstiness") of all line scores.
   - Do NOT use absolute thresholds — z-score each student's (avg, variance)
     against the class distribution for that specific question, and also
     record distance to the AI reference solution's own (avg, variance) as a
     calibration anchor.
   - Do NOT use commercial chat APIs (OpenAI/Gemini/Groq) for this — they
     don't expose raw logprobs needed for perplexity. Local HF model only.
     If a laptop can't run it, HF free Inference API is the fallback, same
     model name, same code path.
   - Research backing: AAAI 2024 paper "Detecting AI-Generated Code
     Assignments Using Perplexity of Large Language Models" confirms
     avg+variance+burstiness combined score is the right design (raised AUC
     from 0.56 baseline to 0.87). A 2025 paper found perplexity ALONE has
     limited standalone accuracy — this is exactly why it's combined with
     the similarity model's score, never used by itself to flag.

## Flag scoring formula
flag_score = w1*peer_similarity + w2*ai_reference_similarity + w3*perplexity_signal
Starting weights: w1=0.4, w2=0.35, w3=0.25 — TUNE these after first real run,
don't hardcode as final. Store each weighted component separately in DB so
dashboard can show "which model contributed what %".

## Pages needed (frontend)
- /login, /signup            — role-based (professor / TA / student), restrict
                                 signup to college email domain
- /professor/dashboard        — list of assignments, create new
- /professor/assignments/new  — upload PDF, add questions, set deadlines
- /professor/questions/:id    — upload AI reference solution for a question
- /professor/flags            — flagged students list, sorted by flag_score
- /professor/flags/:studentId — score breakdown by model %, matched peer name,
                                 side-by-side diff viewer, mark reviewed/dismissed
- /student/dashboard          — list of assignments/questions, deadlines
- /student/questions/:id      — upload submission for that question
(TA sees same pages as professor except cannot create assignments — reuse
components with a role check, don't build separate TA pages)

## Auth
Recommend Supabase Auth (free tier) instead of hand-rolled JWT — saves hours,
gives email/password + role metadata + row-level security for free. Roles:
professor, ta, student, stored as a custom claim / profiles table row.
If Supabase is rejected by team, fallback is FastAPI + JWT + bcrypt, roughly
+2.5 hrs of extra work vs Supabase.

## Repo structure (GitHub)
ll-suffering-dsa-portal/
├── frontend/                          React + Tailwind (Vite)
│   ├── src/pages/                     Login, Signup, ProfessorDashboard,
│   │                                  AssignmentCreate, QuestionDetail,
│   │                                  StudentDashboard, SubmissionUpload,
│   │                                  FlaggedStudents, DiffViewer
│   ├── src/components/                Navbar, RoleGuard, FileUploader,
│   │                                  ScoreBadge
│   ├── src/api/client.js              wraps calls to backend + supabase
│   ├── package.json / tailwind.config.js / vite.config.js
├── backend/                           FastAPI
│   ├── app/main.py                    app entrypoint, router registration
│   ├── app/auth.py                    role check / Supabase token verify
│   ├── app/models.py                  DB models (SQLAlchemy)
│   ├── app/schemas.py                 Pydantic request/response schemas
│   ├── app/routers/auth.py            login/signup routes (if not Supabase)
│   ├── app/routers/assignments.py     CRUD for assignments/questions
│   ├── app/routers/submissions.py     student upload endpoint
│   ├── app/routers/flags.py           GET flagged students, POST run-analysis
│   ├── app/services/similarity_service.py   wraps copydetect
│   ├── app/services/perplexity_service.py   wraps codegen-350M-multi
│   ├── app/services/flag_scoring.py         combines both -> flag_summary rows
│   ├── app/db.py                      DB session/connection
│   ├── app/storage.py                 file upload helpers (Supabase storage)
│   ├── scripts/run_analysis.py        batch job entrypoint, run post-deadline
│   ├── requirements.txt
│   ├── Dockerfile
├── .env.example                       SUPABASE_URL, SUPABASE_KEY, DB_URL, etc
├── .gitignore                         node_modules, __pycache__, .env, *.pt
├── README.md
├── HANDOFF.md                         (this file, keep updated)
└── cyhi-logs/                         (already set up, do not touch manually)

## DB tables (core)
users(id, name, email, role)
assignments(id, title, pdf_url, deadline, created_by)
questions(id, assignment_id, number, description, ai_reference_url)
submissions(id, question_id, student_id, file_url, language, submitted_at)
similarity_pairs(id, question_id, student_a_id, student_b_id, score, match_regions_json)
ai_similarity(id, question_id, student_id, score, match_regions_json)
perplexity_scores(id, submission_id, avg_ppl, variance_ppl, zscore_avg, zscore_variance)
flag_summary(student_id, question_id, total_score, peer_weight_pct, ai_ref_weight_pct,
             perplexity_weight_pct, top_matched_peer_id, status)

## Deployment plan (all free tier — see RESOURCES.md for the full account list)
- Frontend  -> Vercel (deploy React build straight from GitHub, free)
- Backend   -> Render free web service (FastAPI) — KEEP THIS LIGHT,
               do not load PolyCoder-160M inside the main API process,
               Render's free tier gives only ~512MB RAM and the model's
               ~700MB weights alone will crash it.
- Perplexity model -> host separately on Hugging Face Spaces (free CPU
               Basic tier, much more RAM headroom) running PolyCoder-160M
               behind a small FastAPI endpoint; main backend calls it over
               HTTP during the post-deadline batch job. Do not skip this
               separation — it's the difference between the backend staying
               up and it OOM-crashing on Render's free tier.
- DB + file storage -> Supabase free tier (Postgres + storage bucket for PDFs
               and submitted code files), also doubles as auth provider.
- Analysis job trigger -> a "Run Analysis" button on the professor dashboard
               that POSTs to /flags/run-analysis for a question; do NOT run
               it live on every submission (O(n^2) pairwise, batch only).

## Free resources required
Full list with signup links and free-tier limits is in `RESOURCES.md` —
everything in this project (hosting, DB, auth, storage, both models) is
zero-cost on free tiers. No credit card, no paid API keys, no domain
purchase needed anywhere.

## Next 3 things
1. Scaffold backend repo structure + DB models + Supabase connection.
2. Build similarity_service.py (copydetect wrapper) and perplexity_service.py
   (codegen-350M-multi wrapper) as standalone scripts first, test on a few
   sample files, BEFORE wiring into API routes.
3. Scaffold frontend pages with dummy data, wire auth (Supabase), then connect
   real endpoints last.

## Decisions (and why)
- Dropped the separate watermark-detection model — team confirmed only 2
  models: similarity + perplexity. Do not reintroduce a 3rd model.
- Dropped boilerplate-exclusion logic — sir gives no starter code, so it's
  unnecessary complexity for the 20hr budget.
- Chose self-hosted HF model over any commercial API for perplexity because
  commercial chat APIs don't expose raw logprobs — this is a hard constraint,
  not a preference.
- Switched perplexity model from codegen-350M-multi to PolyCoder-160M once
  the team confirmed DSA submissions are C/C++ only — PolyCoder was trained
  on C and C++ specifically (among 12 languages) and is smaller (160M vs
  350M), so it's a strictly better fit now that the language is narrowed.
  Do not swap back without a reason tied to real accuracy testing.
- Confirmed 150 students does NOT require sharding/grouping the DB or
  storage — real usage is a few percent of Supabase's free tier (see
  RESOURCES.md and POLYCODER_GUIDE.md capacity note for the math). Do not
  add group-based data partitioning; it was considered and rejected as
  unnecessary complexity at this scale.
- Chose Supabase over hand-rolled auth/DB/storage to save setup hours given
  the 20-hour budget — revisit only if team already knows Postgres+JWT well
  enough to be faster than learning Supabase.
- Batch job runs only after deadline, triggered manually by professor/TA, not
  on every submission — pairwise similarity is O(n^2), too expensive live.

## Don't retry
- Don't try to get token-level logprobs from OpenAI/Gemini/Groq chat APIs for
  the perplexity model — confirmed not available for free tiers, wasted effort.
- Don't build a custom fingerprinting/winnowing algorithm from scratch —
  copydetect already implements this correctly, reinventing it burns hours
  for no gain within a 20hr hackathon budget.
- Don't run the full analysis pipeline synchronously inside a request handler
  — it will time out on free-tier hosting; always a background/batch job.
