# Resources Required — all free tier, no credit card needed anywhere

Everything below is free. Nothing in this project requires a paid plan, a
paid API key, or a purchased domain. If any step below ever asks for billing
details, stop and flag it to the team — it means a paid tier was selected by
mistake.

## Accounts to create (do this first — see ISSUES.md #23)

| Service | What it's for | Free tier limit (as of this build) | Card required? |
|---|---|---|---|
| [GitHub](https://github.com) | Code hosting, Actions CI | 2000 CI minutes/month (private repos), unlimited public repos | No |
| [Vercel](https://vercel.com) | Frontend hosting | Generous free hobby tier, auto-deploy from GitHub | No |
| [Render](https://render.com) | Backend (FastAPI) hosting | Free web service, ~512MB RAM, sleeps after 15 min idle, 750 hrs/month | No |
| [Supabase](https://supabase.com) | Postgres DB + Auth + file Storage | 500MB DB, 1GB storage, 50k monthly active auth users | No |
| [Hugging Face](https://huggingface.co) | Hosting the PolyCoder model as a Space | Free CPU Basic Space (2 vCPU, 16GB RAM) | No |

That's the entire account list. Five signups, all free, and you're done.

## Models used (both free, open-weight, no API key)

1. **Similarity detection** — `copydetect` (Python package, MIT-licensed,
   `pip install copydetect`). Not a hosted model — runs as plain Python
   inside your own backend, no external calls, no rate limits.

2. **Perplexity detection** — [`NinedayWang/PolyCoder-160M`](https://huggingface.co/NinedayWang/PolyCoder-160M)
   on Hugging Face. Open weights, free to download and run. 160M
   parameters (~700MB), trained on 249GB of code across 12 languages
   **including C and C++** — matches your course exactly. Requires
   `transformers>=4.23.0`. No API key needed to download or run it; if
   you host it on a HF Space (recommended — see below), that's also free.

Why not a commercial API (OpenAI/Gemini/Claude/Groq) for perplexity: those
don't expose raw token log-probabilities on their free tiers, which is what
a perplexity calculation actually needs. Self-hosting PolyCoder is not just
the free option, it's the only option that gives you the right kind of
output at all.

## Libraries (all free, installed via `pip`/`npm`, no license cost)

**Backend (`requirements.txt`):**
- `fastapi`, `uvicorn` — API framework
- `sqlalchemy` — DB ORM
- `pydantic` — request/response schemas
- `copydetect` — similarity detection
- `transformers>=4.23.0`, `torch` — perplexity model (only needed in the
  HF Space and for local testing, NOT in the main Render backend)
- `supabase` (Python client) — if using Supabase Auth/Storage directly
  from the backend
- `python-multipart` — file upload handling in FastAPI

**Frontend (`package.json`):**
- `react`, `react-dom`, `react-router-dom`
- `tailwindcss`
- `@supabase/supabase-js` — auth + storage client
- No paid UI kit needed — plain Tailwind components are enough for a
  20-hour build.

## Why this split keeps everything free

The one thing that could break "free" is RAM: PolyCoder's ~700MB of weights
won't fit comfortably in Render's free ~512MB backend. That's why the model
runs in its own Hugging Face Space (16GB RAM, free CPU tier) instead of
inside the main API — the main backend just makes an HTTP call to it. Keep
this split; loading PolyCoder directly into the Render backend process is
the most likely way this project accidentally needs a paid tier.

## Not needed / explicitly avoid

- No paid domain — use the free subdomains every service above gives you
  (`*.vercel.app`, `*.onrender.com`, `*.hf.space`).
- No paid database — Supabase free tier's 500MB is plenty for a single
  class's submissions and metadata.
- No GPU anywhere — PolyCoder-160M and copydetect both run fine on free CPU
  tiers at this scale (one class, batch job after each deadline, not live).
