# PolyCoder Implementation Guide

Reference implementation for `backend/app/services/perplexity_service.py`
(local/testing) and the Hugging Face Space (production, see ISSUES.md #22).
This is the canonical version — port from here, don't rewrite from scratch.

Model: `NinedayWang/PolyCoder-160M` — GPT-NeoX architecture, 160M params,
trained on 249GB of code across 12 languages including C and C++. Requires
`transformers>=4.23.0`.

## Capacity note (150 students, resolved 2026-09-12)
Storage and compute are NOT a constraint at 150 students — do not shard data
across groups for technical reasons. Numbers:
- Supabase DB: ~7,500 submission rows across a semester, well under 5MB.
- Supabase Storage: ~7,500 files × ~10KB avg ≈ 75MB, under the 1GB free tier.
- Pairwise similarity: 150×149/2 ≈ 11,175 pairs/question, fingerprint
  comparison is cheap, finishes in well under a minute.
- Perplexity: ~150 files × 2-5s each ≈ 5-12 min/question, fine as an async
  background batch job.
Grouping by lab section is still fine as a TA-workflow/ownership choice for
interviews — just don't build it into the DB/storage layer.

## Step 1 — Install
```bash
pip install "transformers>=4.23.0" torch
```

## Step 2 — Load model + tokenizer once at module level
```python
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

MODEL_NAME = "NinedayWang/PolyCoder-160M"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
model.eval()
```
Never reload per-request — load once at startup.

## Step 3 — Per-line perplexity
```python
import math

def line_perplexity(line: str) -> float | None:
    ids = tokenizer(line, return_tensors="pt")["input_ids"]
    if ids.shape[1] < 2:
        return None
    with torch.no_grad():
        loss = model(ids, labels=ids).loss
    return math.exp(loss.item())
```

## Step 4 — Per-file aggregation (avg + variance)
```python
import statistics

def file_stats(filepath: str) -> dict:
    scores = []
    with open(filepath) as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            ppl = line_perplexity(line)
            if ppl is not None:
                scores.append(ppl)
    return {
        "avg": statistics.mean(scores),
        "variance": statistics.pvariance(scores),
        "n_lines": len(scores),
    }
```

## Step 5 — Z-score against the class for that question
```python
def zscore(value: float, class_values: list[float]) -> float:
    mu = statistics.mean(class_values)
    sigma = statistics.pstdev(class_values) or 1e-6
    return (value - mu) / sigma
```
Collect `avg` from every submission for a question into `class_values`
before scoring individuals — the flag signal is relative-to-classmates, not
an absolute cutoff, because difficulty varies per question.

## Step 6 — Hugging Face Space endpoint (production) — ACTUAL, built 2026-09-12
The team's Space (`DSA-Cheating-Detector`) was created via HF's Gradio
template, not Docker+FastAPI as originally sketched here — so the real
implementation uses Gradio's `api_name` feature instead of a raw REST route.
Functionally equivalent, just a different calling convention (Step 7).
Files live in `hf-space/` in the main repo — push them into the Space's own
git repo (it's separate from this GitHub repo, cloned via the URL HF gave
you when you created it):
```python
# hf-space/app.py — full working version, see that file for the real one
import gradio as gr
# ... model loading + line_perplexity from Steps 2-3 ...

def score(code: str) -> str:
    # same logic as file_stats(), but takes/returns a string since this
    # crosses an HTTP boundary — see hf-space/app.py for the full body
    ...

demo = gr.Interface(fn=score, inputs=..., outputs=..., api_name="score")
demo.launch()
```
Deployed as a free CPU Basic Space. Render's free backend must NOT load
these weights in-process (~700MB won't fit in ~512MB RAM) — it calls this
Space instead.

## Step 7 — Backend calling the Space — ACTUAL, via gradio_client
```python
from gradio_client import Client
import json

def get_perplexity_stats(code: str) -> dict:
    client = Client("your-username/DSA-Cheating-Detector")  # public Space, no token needed
    result_json = client.predict(code, api_name="/score")
    return json.loads(result_json)
```

## C/C++ tokenization note
PolyCoder's BPE tokenizer handles C/C++ syntax fine with no preprocessing
needed (braces, `->`, pointers, `#include`/`#define` all tokenize normally —
it was trained on this). If real score distributions show pure-syntax lines
(`{`, `}`, `;`, bare `#include` lines) dominating and flattening the signal,
consider excluding them the same way blank lines are excluded — but verify
against real samples first, don't add this preemptively.

## Testing checklist before considering the perplexity service done
- [ ] Runs on a real ~50-line C/C++ submission in under ~5s on CPU
- [ ] Blank lines confirmed excluded (unit test)
- [ ] A known AI-generated sample (the professor's reference solution) and a
      scrappy real student file produce visibly different avg/variance
- [ ] Z-scoring against a small synthetic class list produces sane numbers
      (not all zeros, not all identical)
