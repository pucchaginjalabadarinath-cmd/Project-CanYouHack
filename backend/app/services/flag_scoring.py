"""
Flag scoring. Per ISSUES.md #10.

Combines three already-computed signals into one flag_score per
(student, question):
  - peer similarity      (SimilarityPair rows - from similarity_service.py, #8)
  - AI-reference similarity (AiSimilarity rows - from similarity_service.py, #8)
  - perplexity/AI-likelihood (PerplexityScore rows - from perplexity_service.py, #9)

This file only COMBINES those outputs - it never runs a detection model
itself. scripts/run_analysis.py (#12) is what calls similarity_service and
perplexity_service first, then calls compute_flags_for_question() here.
"""

from typing import Optional

from sqlalchemy.orm import Session

from ..models import AiSimilarity, FlagSummary, PerplexityScore, SimilarityPair, Submission

# Exposed as named constants, not magic numbers inline, per ISSUES.md #10.
# Each is that signal's MAXIMUM possible share of total_score, reached only
# when the raw signal is fully saturated (1.0). Sum to 1.0.
PEER_SIMILARITY_WEIGHT = 0.40
AI_REFERENCE_WEIGHT = 0.35
PERPLEXITY_WEIGHT = 0.25

# How many class standard deviations below the mean counts as "fully
# suspicious" (perplexity_signal saturates at 1.0 at this point). A round
# starting number - POLYCODER_GUIDE.md's calibration-set step (hand-written
# vs AI-generated C solutions for the same problems) should be used to
# tighten this once real data exists.
ZSCORE_SATURATION_POINT = 3.0


def _max_peer_similarity(
    pairs: list, student_id: str
) -> tuple:
    """
    Highest similarity score involving this student across all peer pairs
    for the question, plus which OTHER student that was (for
    top_matched_peer_id). A student can appear as either side of a
    SimilarityPair row, so both are checked.
    Returns (0.0, None) if this student has no peer-similarity rows at all.
    """
    best_score = 0.0
    best_peer_id: Optional[str] = None
    for pair in pairs:
        if pair.student_a_id == student_id:
            other, score = pair.student_b_id, pair.score
        elif pair.student_b_id == student_id:
            other, score = pair.student_a_id, pair.score
        else:
            continue
        if score > best_score:
            best_score, best_peer_id = score, other
    return best_score, best_peer_id


def perplexity_signal_from_zscores(zscore_avg: float, zscore_variance: float) -> float:
    """
    Converts the two raw z-scores (see perplexity_service.zscore_against_class
    for what they mean and why negative is the suspicious direction) into
    one 0-1 "how AI-like is this" signal.

    Only NEGATIVE z-scores count - a positive z-score (messier than the
    class average, i.e. clearly human) contributes exactly 0, it never
    cancels out a suspicious reading from the other component.

    Weighted 60/40 toward avg-perplexity over variance/burstiness: average
    perplexity is the primary, better-established signal in perplexity-
    based AI-text-detection research; burstiness is the confirming
    secondary signal (see HANDOFF.md's discussion of both). Each z-score is
    clamped to ZSCORE_SATURATION_POINT std deviations before combining, so
    one wildly extreme outlier submission can't blow the scale for
    everyone else in the same batch.
    """

    def _suspicious_fraction(zscore: float) -> float:
        if zscore >= 0:
            return 0.0
        return min(-zscore, ZSCORE_SATURATION_POINT) / ZSCORE_SATURATION_POINT

    return 0.6 * _suspicious_fraction(zscore_avg) + 0.4 * _suspicious_fraction(zscore_variance)


def compute_flags_for_question(db: Session, question_id: str) -> list:
    """
    Recomputes every FlagSummary row for one question from the
    SimilarityPair / AiSimilarity / PerplexityScore rows that already exist
    for it.

    Idempotent per ISSUES.md #12's acceptance criteria ("running it twice
    on the same question is idempotent - upsert or delete-then-insert"):
    existing FlagSummary rows for this question are deleted and rebuilt
    every call rather than appended to.
    """
    db.query(FlagSummary).filter(FlagSummary.question_id == question_id).delete()

    submissions = (
        db.query(Submission).filter(Submission.question_id == question_id).all()
    )
    similarity_pairs = (
        db.query(SimilarityPair).filter(SimilarityPair.question_id == question_id).all()
    )
    ai_similarities = {
        row.student_id: row
        for row in db.query(AiSimilarity)
        .filter(AiSimilarity.question_id == question_id)
        .all()
    }

    created = []

    for submission in submissions:
        student_id = submission.student_id

        peer_score, top_matched_peer_id = _max_peer_similarity(similarity_pairs, student_id)

        ai_similarity_row = ai_similarities.get(student_id)
        ai_score = ai_similarity_row.score if ai_similarity_row is not None else 0.0

        perplexity_score: Optional[PerplexityScore] = submission.perplexity_score
        if perplexity_score is not None:
            perplexity_signal = perplexity_signal_from_zscores(
                perplexity_score.zscore_avg, perplexity_score.zscore_variance
            )
        else:
            # No perplexity row yet (score not computed for this
            # submission) - contributes nothing rather than being treated
            # as "average" or "suspicious".
            perplexity_signal = 0.0

        peer_component = PEER_SIMILARITY_WEIGHT * peer_score
        ai_component = AI_REFERENCE_WEIGHT * ai_score
        perplexity_component = PERPLEXITY_WEIGHT * perplexity_signal

        total_score = peer_component + ai_component + perplexity_component

        # The % breakdown is each component's SHARE of total_score, not the
        # fixed weight constants above - this is what makes ISSUES.md #10's
        # acceptance criterion true: a student flagged ONLY by perplexity
        # has peer_component == 0, so peer_weight_pct comes out to 0
        # regardless of what PEER_SIMILARITY_WEIGHT is set to. Falls back
        # to an even 0/0/0 split if total_score is 0 (student isn't
        # flagged by anything) to avoid a division by zero.
        if total_score > 0:
            peer_weight_pct = 100 * peer_component / total_score
            ai_ref_weight_pct = 100 * ai_component / total_score
            perplexity_weight_pct = 100 * perplexity_component / total_score
        else:
            peer_weight_pct = ai_ref_weight_pct = perplexity_weight_pct = 0.0

        flag_summary = FlagSummary(
            student_id=student_id,
            question_id=question_id,
            total_score=total_score,
            peer_weight_pct=peer_weight_pct,
            ai_ref_weight_pct=ai_ref_weight_pct,
            perplexity_weight_pct=perplexity_weight_pct,
            top_matched_peer_id=top_matched_peer_id,
            status="pending",
        )
        db.add(flag_summary)
        created.append(flag_summary)

    db.commit()
    for row in created:
        db.refresh(row)
    return created
