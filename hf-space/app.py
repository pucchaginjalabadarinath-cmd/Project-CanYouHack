"""
Hugging Face Space - PolyCoder perplexity scorer for the DSA Cheating
Detector project. Reference walkthrough this was built from lives in
POLYCODER_GUIDE.md in the main repo.

Exposes one function, `score`, as a Gradio API endpoint (api_name="score")
so the main FastAPI backend can call it without a human touching the UI -
see "Calling this from the backend" at the bottom of this file.
"""

import json
import math
import statistics

import gradio as gr
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = "NinedayWang/PolyCoder-160M"

# Load once at startup, not per-request - this is the expensive part.
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
model.eval()


def line_perplexity(line: str):
    ids = tokenizer(line, return_tensors="pt")["input_ids"]
    if ids.shape[1] < 2:
        return None  # too short to score meaningfully
    with torch.no_grad():
        loss = model(ids, labels=ids).loss
    return math.exp(loss.item())


def score(code: str) -> str:
    """
    Takes raw C/C++ source as a single string, returns a JSON string:
        {"avg": float, "variance": float, "n_lines": int}
    Blank lines are skipped, matching perplexity_service.py's design in the
    main repo (ISSUES.md #9).
    """
    scores = []
    for raw_line in code.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        ppl = line_perplexity(line)
        if ppl is not None:
            scores.append(ppl)

    if not scores:
        return json.dumps({"avg": None, "variance": None, "n_lines": 0})

    return json.dumps({
        "avg": statistics.mean(scores),
        "variance": statistics.pvariance(scores),
        "n_lines": len(scores),
    })


demo = gr.Interface(
    fn=score,
    inputs=gr.Textbox(label="C/C++ code", lines=20, placeholder="Paste a submission here..."),
    outputs=gr.Textbox(label="Perplexity stats (JSON)"),
    title="DSA Cheating Detector — Perplexity Scorer",
    description=(
        "Internal scoring endpoint for the main backend. The text box above "
        "is just for manually checking the model works - the real caller is "
        "the FastAPI backend, via the gradio_client package."
    ),
    api_name="score",
)

if __name__ == "__main__":
    demo.launch()

# --- Calling this from the backend (perplexity_service.py, ISSUES.md #9) ---
#
#   from gradio_client import Client
#   client = Client("your-username/DSA-Cheating-Detector")
#   result_json = client.predict(code_string, api_name="/score")
#   stats = json.loads(result_json)
#
# `gradio_client` is already in backend/requirements.txt. If the Space is
# private, pass hf_token="hf_..." to Client(); public Spaces need no token.
