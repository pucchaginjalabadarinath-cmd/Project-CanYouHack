"""
Batch analysis entry point. Per ISSUES.md #12.

Given a question_id: downloads all its submissions + the AI reference (if
one was uploaded), runs similarity_service (#8) and perplexity_service
(#9), persists their outputs as SimilarityPair / AiSimilarity /
PerplexityScore rows, then calls flag_scoring.compute_flags_for_question
(#10) to (re)build the FlagSummary rows the flags router (#11) serves.

Two ways to run this:
  - Standalone, for local testing, exactly as ISSUES.md #12 specifies:
        cd backend && python scripts/run_analysis.py --question-id <id>
    (also works as `python -m scripts.run_analysis --question-id <id>`)
  - As a plain function call from the background task in
    routers/flags.py's POST /questions/{id}/run-analysis, which imports
    it as `from scripts.run_analysis import run_analysis`.

Path note: `scripts/` and `app/` are sibling top-level directories under
backend/, not nested packages of each other, so relative imports
(`..app...`, `...scripts...`) can NEVER cross that boundary correctly -
don't use them here or anywhere that imports this module. The sys.path
line right below makes plain `python scripts/run_analysis.py` (run from
anywhere, not just from backend/) resolve `app...` imports correctly too.

Idempotency (ISSUES.md #12's acceptance criteria - "running it twice on
the same question doesn't duplicate rows, upsert or delete-then-insert"):
every table this writes to is cleared for this question_id (or this
question's submission_ids, for PerplexityScore) first, then rebuilt from
scratch, every run. This also correctly handles a submission being
edited/removed between runs, which a per-row upsert wouldn't - deleted
submissions just don't get new rows, and their stale old rows are gone
too. flag_scoring.compute_flags_for_question() already follows this same
delete-then-insert pattern for FlagSummary itself.
"""

import argparse
import logging
import os
import sys
import tempfile
from typing import Dict, List, Optional

# Makes `from app...` resolve correctly no matter where this script is
# invoked from (cwd, `-m`, or a direct path like `python
# scripts/run_analysis.py`) by putting backend/ - this file's parent's
# parent - on sys.path before any app.* import below is attempted.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session  # noqa: E402

from app import storage  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    AiSimilarity,
    PerplexityScore,
    Question,
    SimilarityPair,
    Submission,
)
from app.services import flag_scoring, perplexity_service, similarity_service  # noqa: E402

logger = logging.getLogger(__name__)


def _download_submissions(submissions: List[Submission], tmpdir: str) -> Dict[str, str]:
    """
    Downloads every submission's file into `tmpdir`, keyed by student_id -
    the shape both similarity_service.compare_all_students() and the
    per-submission perplexity_service.file_stats() calls below expect.
    Preserves the submission's own extension since copydetect
    (similarity_service, #8) picks its comparison strategy off it.
    """
    file_paths = {}
    for submission in submissions:
        ext = ".cpp" if submission.language == "cpp" else ".c"
        local_path = os.path.join(tmpdir, f"{submission.student_id}{ext}")
        file_bytes = storage.download_file(submission.file_url)
        with open(local_path, "wb") as f:
            f.write(file_bytes)
        file_paths[submission.student_id] = local_path
    return file_paths


def _download_ai_reference(question: Question, tmpdir: str) -> Optional[str]:
    if not question.ai_reference_url:
        return None
    local_path = os.path.join(tmpdir, "ai_reference.c")
    file_bytes = storage.download_file(question.ai_reference_url)
    with open(local_path, "wb") as f:
        f.write(file_bytes)
    return local_path


def _replace_question_rows(db: Session, model, question_id: str, rows: list) -> None:
    """
    Shared delete-then-insert helper - the idempotency mechanism required
    by ISSUES.md #12. Used for SimilarityPair and AiSimilarity, both of
    which are keyed directly by question_id. PerplexityScore is handled
    separately below since it's keyed by submission_id instead.
    """
    db.query(model).filter(model.question_id == question_id).delete()
    for row in rows:
        db.add(row)
    db.commit()


def run_analysis(question_id: str, db: Session) -> None:
    logger.info("Starting analysis for question %s", question_id)

    question = db.query(Question).filter(Question.id == question_id).first()
    if question is None:
        raise ValueError(f"question {question_id} not found")

    submissions = (
        db.query(Submission).filter(Submission.question_id == question_id).all()
    )
    if not submissions:
        logger.info("No submissions for question %s - nothing to analyze", question_id)
        # Still rebuild flags (as empty) so re-running after every
        # submission was removed correctly clears out stale FlagSummary
        # rows too, rather than leaving results from a previous run.
        flag_scoring.compute_flags_for_question(db, question_id)
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        file_paths = _download_submissions(submissions, tmpdir)
        reference_path = _download_ai_reference(question, tmpdir)

        # --- Peer-vs-peer similarity (ISSUES.md #8) ---
        logger.info("Running compare_all_students for %d submissions", len(file_paths))
        peer_results = similarity_service.compare_all_students(file_paths)
        similarity_pairs = [
            SimilarityPair(
                question_id=question_id,
                student_a_id=r["student_a_id"],
                student_b_id=r["student_b_id"],
                score=r["score"],
                match_regions_json=r.get("match_regions_json"),
            )
            for r in peer_results
        ]
        _replace_question_rows(db, SimilarityPair, question_id, similarity_pairs)

        # --- Student-vs-AI-reference similarity (ISSUES.md #8) ---
        if reference_path is not None:
            logger.info("Running compare_to_reference against the AI reference solution")
            ai_ref_results = similarity_service.compare_to_reference(file_paths, reference_path)
            ai_similarities = [
                AiSimilarity(
                    question_id=question_id,
                    student_id=r["student_id"],
                    score=r["score"],
                    match_regions_json=r.get("match_regions_json"),
                )
                for r in ai_ref_results
            ]
        else:
            logger.info("Question has no AI reference solution - skipping AI-similarity")
            ai_similarities = []
        _replace_question_rows(db, AiSimilarity, question_id, ai_similarities)

        # --- Perplexity (ISSUES.md #9) ---
        logger.info("Computing perplexity stats for each submission")
        raw_stats = {}
        for submission in submissions:
            path = file_paths.get(submission.student_id)
            if path is None:
                continue
            raw_stats[submission.id] = perplexity_service.file_stats(path)

        all_class_stats = list(raw_stats.values())

        submission_ids = [s.id for s in submissions]
        db.query(PerplexityScore).filter(
            PerplexityScore.submission_id.in_(submission_ids)
        ).delete(synchronize_session=False)

        for submission in submissions:
            stats = raw_stats.get(submission.id)
            if stats is None:
                continue
            zscores = perplexity_service.zscore_against_class(stats, all_class_stats)
            db.add(
                PerplexityScore(
                    submission_id=submission.id,
                    avg_ppl=stats.get("avg") or 0.0,
                    variance_ppl=stats.get("variance") or 0.0,
                    zscore_avg=zscores["zscore_avg"],
                    zscore_variance=zscores["zscore_variance"],
                )
            )
        db.commit()

        # --- Combine into FlagSummary rows (ISSUES.md #10) ---
        # compute_flags_for_question() is itself delete-then-insert per
        # question_id, so calling it again here on every run is what
        # makes THIS whole function idempotent overall.
        logger.info("Computing flag scores")
        flag_scoring.compute_flags_for_question(db, question_id)

    logger.info("Analysis complete for question %s", question_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="Run cheating-detection analysis for one question."
    )
    parser.add_argument("--question-id", required=True, help="Question ID to analyze")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        run_analysis(args.question_id, db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
