---
title: DSA Cheating Detector
emoji: 🕵️
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
---

# DSA Cheating Detector — Perplexity Scoring Space

Internal scoring service for the LL suffering team's DSA Assignment Portal.
Loads `NinedayWang/PolyCoder-160M` and scores C/C++ code for per-line
perplexity (avg + variance), used as one of two plagiarism/AI-use signals
alongside the similarity model in the main backend.

Called via the `gradio_client` package from the main FastAPI backend's
`perplexity_service.py` — not meant for direct manual use, though the UI
above works for a quick manual check.

Full context: see `POLYCODER_GUIDE.md` and `ISSUES.md` (#9, #22) in the main
project repo.
