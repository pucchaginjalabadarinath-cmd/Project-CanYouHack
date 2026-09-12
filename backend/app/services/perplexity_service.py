"""
Perplexity/AI-likelihood service. Per ISSUES.md #9.

Backend note (read before editing):
Default mode calls the hosted HF Space (see hf-space/app.py, ISSUES.md #22)
over the network via gradio_client, because Render's free tier (~512MB RAM)
cannot hold PolyCoder-160M in-process alongside the rest of this API.
line_perplexity() below always runs LOCALLY regardless of that setting -
it's the low-level primitive used for local/offline testing (e.g. a unit
test checking blank-line exclusion shouldn't need network access to the HF
Space), and as the engine behind file_stats() when
PERPLEXITY_BACKEND=local is set for standalone dev work.

Model: NinedayWang/PolyCoder-160M - a causal/GPT-NeoX-style model trained
on multi-language code including C/C++ (see HANDOFF.md for why this was
picked over SantaCoder - submissions here are confirmed C/C++ only).
"""

import json
import math
import os
import statistics
from functools import lru_cache
from pathlib import Path
from typing import Optional

MODEL_NAME = "NinedayWang/PolyCoder-160M"

# "remote" (default) -> call the HF Space. "local" -> load PolyCoder in
# this process (needs `torch` + `transformers` installed - not in
# requirements.txt by default since Render's free tier can't afford the
# RAM; install them yourself for local-only testing).
PERPLEXITY_BACKEND = os.environ.get("PERPLEXITY_BACKEND", "remote").lower()
HF_SPACE_ID = os.environ.get("HF_SPACE_ID")

_tokenizer = None
_model = None


def _load_local_model():
    """Lazy singleton load - only pulled in if line_perplexity() or
    PERPLEXITY_BACKEND=local is actually used, so importing this module
    doesn't require torch/transformers to be installed at all in the
    (default) remote-only deployment."""
    global _tokenizer, _model
    if _model is None:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
        _model.eval()
    return _tokenizer, _model


def line_perplexity(line: str) -> Optional[float]:
    """
    Perplexity of a single line, computed locally. Returns None if the line
    tokenizes to fewer than 2 tokens (too short to score meaningfully) -
    same rule as hf-space/app.py's copy of this function, kept in sync
    deliberately since the Space is the production path and this is the
    reference/test path.
    """
    import torch

    tokenizer, model = _load_local_model()
    ids = tokenizer(line, return_tensors="pt")["input_ids"]
    if ids.shape[1] < 2:
        return None
    with torch.no_grad():
        loss = model(ids, labels=ids).loss
    return math.exp(loss.item())


def _file_stats_local(code: str) -> dict:
    scores = []
    n_lines = 0
    for raw_line in code.splitlines():
        line = raw_line.strip()
        if not line:
            continue  # blank lines excluded, per ISSUES.md #9
        n_lines += 1
        ppl = line_perplexity(line)
        if ppl is not None:
            scores.append(ppl)

    if not scores:
        return {"avg": None, "variance": None, "n_lines": n_lines}
    return {
        "avg": statistics.mean(scores),
        "variance": statistics.pvariance(scores),
        "n_lines": n_lines,
    }


@lru_cache(maxsize=1)
def _get_remote_client():
    from gradio_client import Client

    return Client(HF_SPACE_ID)


def _file_stats_remote(code: str) -> dict:
    if not HF_SPACE_ID:
        raise RuntimeError(
            "HF_SPACE_ID is not set (backend/.env) - required when "
            "PERPLEXITY_BACKEND=remote (the default). Set "
            "PERPLEXITY_BACKEND=local to run PolyCoder in-process instead "
            "(needs torch+transformers installed, ~700MB RAM - fine for a "
            "laptop, NOT for Render's free tier)."
        )
    client = _get_remote_client()
    result_json = client.predict(code, api_name="/score")
    return json.loads(result_json)


def file_stats(filepath: str) -> dict:
    """
    Returns {"avg": float|None, "variance": float|None, "n_lines": int} for
    the given source file - blank lines skipped either way. Routes to the
    HF Space (default) or an in-process model (PERPLEXITY_BACKEND=local)
    depending on the env var above.
    """
    code = Path(filepath).read_text(encoding="utf-8", errors="replace")
    if PERPLEXITY_BACKEND == "local":
        return _file_stats_local(code)
    return _file_stats_remote(code)


def zscore_against_class(student_stats: dict, all_class_stats: list) -> dict:
    """
    student_stats: one file_stats() dict for the submission being scored.
    all_class_stats: file_stats() dicts for every submission to the SAME
    question (including the student's own one - needed to compute a real
    class mean/stdev to compare against).

    Returns {"zscore_avg": float, "zscore_variance": float}.

    Which direction is suspicious, and why: an LLM always emits the token
    IT considers most probable, so when that same code is fed back through
    a language model, its own tokens score back as high-probability /
    low-perplexity almost everywhere - and consistently so (low variance
    line-to-line, since the model isn't second-guessing itself the way a
    human juggling multiple approaches would). So a submission with
    avg/variance far BELOW the rest of the class on the same question
    (a large NEGATIVE z-score) is the AI-like direction. A submission
    messier than the class average (positive z-score) is not suspicious -
    see flag_scoring.py's perplexity_signal_from_zscores(), which only
    treats negative z-scores as contributing to the flag.

    Falls back to 0.0 when there are fewer than 2 usable data points in
    the class (stdev undefined) or when the student's own value is None
    (e.g. an empty/unscoreable file) - a missing signal should never look
    like "solidly average", it should just not contribute.
    """

    def _zscore(value, population):
        clean = [v for v in population if v is not None]
        if value is None or len(clean) < 2:
            return 0.0
        mean = statistics.mean(clean)
        stdev = statistics.pstdev(clean)
        if stdev == 0:
            return 0.0
        return (value - mean) / stdev

    avg_population = [s.get("avg") for s in all_class_stats]
    variance_population = [s.get("variance") for s in all_class_stats]

    return {
        "zscore_avg": _zscore(student_stats.get("avg"), avg_population),
        "zscore_variance": _zscore(student_stats.get("variance"), variance_population),
    }
