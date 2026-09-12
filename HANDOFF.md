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
