# File Working Guide — for any model/agent continuing this repo

Read `HANDOFF.md` first for full project context. This file tells you, file by
file, HOW to approach implementing each empty stub. Match each file here to
its numbered issue in `ISSUES.md` for the detailed spec — this file is the
"how to think about it", ISSUES.md is the "what exactly to build".

**Before touching any file:** run `cyhi-logs/bin/cyhi status`, read the
handoff and Don't-retry list, and log your turn when you're done (see
`AGENTS.md`). Do not skip this even if you're a different model — it's how
the team tracks who built what.

## Build order (respect this — later files depend on earlier ones)

1. `backend/app/models.py` → 2. `backend/app/db.py` → 3. `backend/app/schemas.py`
→ 4. `backend/app/auth.py` + `routers/auth.py` → 5. `backend/app/storage.py`
→ 6-7. routers (assignments, submissions) → 8-9. services (similarity,
perplexity) → 10. flag_scoring → 11-12. flags router + run_analysis script
→ 13. main.py (wires everything) → then frontend, roughly in the page order
listed in ISSUES.md.

Do NOT start a frontend page that calls an endpoint whose router doesn't
exist yet — build backend-first, or stub the API client with mock data and
clearly mark it `// TODO: replace mock once backend/routers/X exists`.

---

## backend/app/models.py
Start here. Every other backend file imports from this. Write the SQLAlchemy
`Base` classes exactly matching the table list in `HANDOFF.md`'s "DB tables"
section. Don't add columns not listed there without updating HANDOFF.md too —
other files will assume the schema in the handoff is authoritative.

## backend/app/db.py
Small file. One engine, one `SessionLocal`, one `get_db()` generator. Read
`DATABASE_URL` from `os.environ`, fail loudly (raise, don't silently default)
if it's missing — this saved debugging time in similar projects.

## backend/app/schemas.py
Mechanical translation of `models.py` into Pydantic. For every SQLAlchemy
model, write a `*Create` (input, no id) and a `*Out` (output, has id) schema.
`FlagSummaryOut` is the one that needs care — it MUST expose
`peer_weight_pct`, `ai_ref_weight_pct`, `perplexity_weight_pct` as separate
fields, not a combined string, because the frontend `ScoreBadge` renders them
as three separate bars.

## backend/app/auth.py + backend/app/routers/auth.py
Decide Supabase vs hand-rolled FIRST (check HANDOFF.md's Decisions section —
Supabase was the recommendation, don't relitigate unless the team explicitly
changed their mind). Everything downstream (`require_role` dependency) is
imported by every other router, so get this working and tested before moving
to routers.

## backend/app/storage.py
Two functions, both dumb wrappers. Don't add business logic here (e.g. don't
validate file types here — do that in the router that calls it). Keep this
file a thin I/O layer so it's easy to swap Supabase Storage for S3 later if
needed.

## backend/app/routers/assignments.py, submissions.py, flags.py
Standard FastAPI router pattern: `APIRouter()`, path operations, inject
`db: Session = Depends(get_db)` and `user = Depends(require_role(...))`.
Keep business logic (deadline checks, role restrictions) IN the router, not
scattered in the frontend — the frontend should assume the backend is the
source of truth and just display what it's told.

## backend/app/services/similarity_service.py
`pip install copydetect` first, read its docs/README for the exact function
signatures (they may differ slightly from version to version) — don't guess
the API. Test it standalone on two sample files in a scratch script before
wiring it into the service function. This is one of the two core "models" —
get it right in isolation before touching routers.

## backend/app/services/perplexity_service.py
Model is `NinedayWang/PolyCoder-160M` (GPT-NeoX architecture, trained on 12
languages including C and C++ — matches the course exactly, no multi-language
branching needed). `pip install "transformers>=4.23.0" torch` — the version
pin matters, the model card calls it out explicitly.

Two deployment modes for this file, don't conflate them:
1. **Local/standalone mode** (for testing): load the model directly with
   `AutoModelForCausalLM.from_pretrained("NinedayWang/PolyCoder-160M")` at
   module level, not inside a function — reloading per-call is far too slow.
2. **Production mode**: the actual backend on Render should NOT load this
   model in-process (too much RAM for the free tier) — instead this file
   should call the Hugging Face Space endpoint from issue #22 over HTTP.

Write the file so both modes share the same `file_stats()` interface — e.g.
an env var `PERPLEXITY_MODE=local|remote` that picks which code path runs,
so local dev/testing doesn't require deploying the HF Space first.

Test on a real submitted C/C++ file, not a toy string, before considering
this done — short toy strings give misleadingly extreme perplexity values.

## backend/app/services/flag_scoring.py
This file has NO external dependencies (no model calls) — it's pure
arithmetic over the outputs of the two services above. Write it so weights
(`W_PEER = 0.4`, `W_AI_REF = 0.35`, `W_PERPLEXITY = 0.25`) are constants at
the top, easy to tune after seeing real score distributions from a test run.

## backend/scripts/run_analysis.py
This is the glue script. Write it as a function `run_analysis(question_id:
int, db: Session)` first, then add a thin `if __name__ == "__main__":
argparse` wrapper so it's runnable standalone AND importable from the flags
router's background task. Don't write two separate implementations.

## backend/app/main.py
Do this LAST on the backend side, once routers exist — it's just
registration + CORS + health check. Should be short (~30-40 lines).

## frontend/src/api/client.js
Do this early on the frontend side — every page imports from it. One
`fetch`-wrapping function that attaches the auth header, plus a named export
per endpoint. If the matching backend router doesn't exist yet, stub the
function to return realistic mock JSON matching the `*Out` schema shape, with
a `// TODO` comment — this lets frontend pages be built in parallel with the
backend instead of blocking on it.

## frontend/src/components/RoleGuard.jsx, Navbar.jsx
Build these before any page that needs auth-gating — every professor/TA page
will be wrapped in `<RoleGuard allow={["professor","ta"]}>`.

## frontend/src/pages/Login.jsx, Signup.jsx
Standard forms. If using Supabase Auth, use their JS client directly here
rather than routing through your own backend for login/signup.

## frontend/src/pages/ProfessorDashboard.jsx, AssignmentCreate.jsx
Build the list view (Dashboard) before the create form — it's simpler and
lets you sanity-check the API client against real/mock data first.

## frontend/src/pages/QuestionDetail.jsx, SubmissionUpload.jsx, components/FileUploader.jsx
`FileUploader` should be a generic, reusable component (used both here and in
`AssignmentCreate.jsx` for the AI-reference upload) — don't write two
separate upload widgets.

## frontend/src/pages/FlaggedStudents.jsx, components/ScoreBadge.jsx
`ScoreBadge` is a small presentational component (props: `peerPct`,
`aiRefPct`, `perplexityPct`, `total`) — keep it dumb/stateless, all data
fetching happens in the page, not the badge.

## frontend/src/pages/DiffViewer.jsx
This is the most fiddly frontend file. Use the `match_regions_json` shape
that `similarity_service.py` actually outputs (check that file first, don't
assume a shape) — render two code panes with matching line ranges
highlighted in the same color. A basic `<pre>`-based diff with highlighted
`<span>` ranges is enough; don't reach for a heavy diff library given the
time budget.

## frontend/tailwind.config.js, vite.config.js, package.json
Standard Vite + React + Tailwind boilerplate — generate with
`npm create vite@latest` and `npx tailwindcss init` rather than hand-writing,
then adjust paths/content globs to match this repo's `src/` layout.

## backend/requirements.txt, backend/Dockerfile, .env.example files
Fill these in as you go — every time you add an import in a backend file,
add it to `requirements.txt` immediately, don't batch it for later (easy to
forget one and break the Docker build).

---

## When you finish a file
1. Run whatever quick test proves the acceptance criteria in `ISSUES.md` for
   that file.
2. `cyhi-logs/bin/cyhi log --type code --summary "<what you built, how
   complete>" --files <path>`
3. If you made a decision not already in `HANDOFF.md` (e.g. changed a
   library, changed a weight), add it to the Decisions section so the next
   agent doesn't redo the same debate.
