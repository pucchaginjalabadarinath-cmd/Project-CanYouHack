"""
Similarity service - wraps `copydetect`'s low-level API (CodeFingerprint +
compare_files + utils.highlight_overlap), per ISSUES.md #8.

This replaces a previous version of this file that called
`CopyDetector.get_copied_code_list()`. That method is not part of
copydetect's documented API - the real `CopyDetector` class only exposes
`add_file()` / `run()` / `generate_html_report()` (report-generation
usage), with no method that returns a list of per-pair match tuples. That
version would raise AttributeError the first time it actually ran against
the real installed package. The API used here instead is copydetect's own
documented low-level workflow, confirmed against
https://copydetect.readthedocs.io/en/stable/api.html's worked example:

    fp1 = copydetect.CodeFingerprint(path, k, win_size)
    fp2 = copydetect.CodeFingerprint(path, k, win_size)
    token_overlap, similarities, slices = copydetect.compare_files(fp1, fp2)
    html, _ = copydetect.utils.highlight_overlap(fp.raw_code, slice, start_tag, end_tag)

IMPORTANT - match_regions_json shape is unchanged from the previous
(buggy) version on purpose: DiffViewer.jsx and routers/flags.py's
get_flag_diff already read `match_regions_json.html_code_a`,
`.html_code_b`, and `.overlap_tokens` (DiffViewer renders html_code_a/b
with dangerouslySetInnerHTML, expecting copydetect's own highlighted-span
HTML). That frontend contract is already built and wired up, so this file
produces exactly that shape rather than the line-range shape an earlier
draft of this file used - changing it now would break the diff viewer.
highlight_overlap's start/end tags are passed as real HTML (`<mark>`)
here specifically so that contract holds.

Don't retry (per HANDOFF.md):
  - No custom fingerprinting/winnowing algorithm - copydetect already does
    this correctly.
  - No boilerplate-exclusion logic - professor gives no starter code, so
    `boilerplate=[]` throughout.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import copydetect
from copydetect.utils import highlight_overlap

# k-gram size / winnowing window. copydetect's own docs example uses
# (25, 1) for whole files; DSA question submissions are much shorter C/C++
# files, so a smaller k-gram catches shorter copied fragments. Re-tune
# once there's a real submission batch, per HANDOFF.md ("tune after first
# real run").
DEFAULT_K = 15
DEFAULT_WIN_SIZE = 1

_LANGUAGE_BY_EXT = {
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
}

# Real HTML tags (not copydetect's own ">>"/"<<" example markers) so the
# output can be dropped straight into DiffViewer.jsx's
# dangerouslySetInnerHTML, matching that component's own comment
# ("copydetect returns HTML spans with highlight classes").
_HIGHLIGHT_START_TAG = '<mark class="bg-yellow-200 text-yellow-900">'
_HIGHLIGHT_END_TAG = "</mark>"


def _guess_language(path: str) -> Optional[str]:
    """Map a file extension to the pygments lexer name copydetect expects.
    Falls back to None (pygments auto-detects from the filename) for
    anything unrecognized - the portal only accepts C/C++ per
    HANDOFF.md, but this stays permissive."""
    _, ext = os.path.splitext(path)
    return _LANGUAGE_BY_EXT.get(ext.lower())


def _fingerprint(path: str, k: int, win_size: int) -> "copydetect.CodeFingerprint":
    return copydetect.CodeFingerprint(
        path, k, win_size, boilerplate=[], filter=True, language=_guess_language(path)
    )


def _pair_result(
    fp_a: "copydetect.CodeFingerprint", fp_b: "copydetect.CodeFingerprint"
) -> Tuple[float, Dict[str, Any]]:
    """Runs copydetect.compare_files and returns (score, match_regions_json)
    in the exact shape DiffViewer.jsx/flags.py already expect.

    score is the average of copydetect's two directional overlap
    percentages, so identical files score ~1.0 regardless of which side
    is 'a' vs 'b' (compare_files' `similarities` isn't symmetric when the
    two files differ in length).
    """
    token_overlap, similarities, slices = copydetect.compare_files(fp_a, fp_b)
    score = (similarities[0] + similarities[1]) / 2

    html_a, _ = highlight_overlap(
        fp_a.raw_code, slices[0], _HIGHLIGHT_START_TAG, _HIGHLIGHT_END_TAG
    )
    html_b, _ = highlight_overlap(
        fp_b.raw_code, slices[1], _HIGHLIGHT_START_TAG, _HIGHLIGHT_END_TAG
    )

    match_regions = {
        "html_code_a": html_a,
        "html_code_b": html_b,
        "overlap_tokens": int(token_overlap),
    }
    return score, match_regions


def compare_all_students(
    file_paths: Dict[str, str],
    k: int = DEFAULT_K,
    win_size: int = DEFAULT_WIN_SIZE,
) -> List[Dict[str, Any]]:
    """Student-vs-student pairwise similarity for one question.

    file_paths: {student_id: path_to_submission}

    Returns a list of dict rows shaped like `SimilarityPair` (minus id/
    question_id, which the caller fills in when persisting):
        {"student_a_id", "student_b_id", "score", "match_regions_json"}

    Note: which student ends up as "a" vs "b" in any given pair is just
    dict-iteration order, not "the flagged student" - routers/flags.py
    already handles the pair being stored in either order when looking a
    SimilarityPair up for a given flagged student.
    """
    student_ids = list(file_paths.keys())
    fingerprints = {sid: _fingerprint(file_paths[sid], k, win_size) for sid in student_ids}

    rows: List[Dict[str, Any]] = []
    for i in range(len(student_ids)):
        for j in range(i + 1, len(student_ids)):
            sid_a, sid_b = student_ids[i], student_ids[j]
            score, match_regions = _pair_result(fingerprints[sid_a], fingerprints[sid_b])
            rows.append(
                {
                    "student_a_id": sid_a,
                    "student_b_id": sid_b,
                    "score": score,
                    "match_regions_json": match_regions,
                }
            )
    return rows


def compare_to_reference(
    file_paths: Dict[str, str],
    reference_path: str,
    k: int = DEFAULT_K,
    win_size: int = DEFAULT_WIN_SIZE,
) -> List[Dict[str, Any]]:
    """Student-vs-professor's-AI-reference similarity for one question.

    Returns a list of dict rows shaped like `AiSimilarity` (minus id/
    question_id):
        {"student_id", "score", "match_regions_json"}

    Unlike compare_all_students, the student is always fp_a here (so
    match_regions_json.html_code_a is always the student's code and
    .html_code_b is always the AI reference's - DiffViewer.jsx's AI
    Reference pane relies on that fixed order, since there's no second
    student id to disambiguate against).
    """
    reference_fp = _fingerprint(reference_path, k, win_size)

    rows: List[Dict[str, Any]] = []
    for student_id, path in file_paths.items():
        student_fp = _fingerprint(path, k, win_size)
        score, match_regions = _pair_result(student_fp, reference_fp)
        rows.append(
            {
                "student_id": student_id,
                "score": score,
                "match_regions_json": match_regions,
            }
        )
    return rows


if __name__ == "__main__":
    # Standalone smoke test per FILE_WORKING_GUIDE.md ("test it standalone
    # on two sample files before wiring it into the service function") and
    # ISSUES.md #8's acceptance criteria. Run with:
    #   python -m app.services.similarity_service
    import tempfile

    identical_code = """
#include <stdio.h>
int add(int a, int b) {
    int result = a + b;
    return result;
}
int main() {
    printf("%d\\n", add(2, 3));
    return 0;
}
""".strip()

    unrelated_code = """
#include <stdio.h>
int main() {
    for (int i = 0; i < 10; i++) {
        printf("row %d\\n", i);
    }
    return 0;
}
""".strip()

    with tempfile.TemporaryDirectory() as tmp:
        p_a = os.path.join(tmp, "a.c")
        p_b = os.path.join(tmp, "b.c")
        p_c = os.path.join(tmp, "c.c")
        for p, code in ((p_a, identical_code), (p_b, identical_code), (p_c, unrelated_code)):
            with open(p, "w") as f:
                f.write(code)

        identical_rows = compare_all_students({"s1": p_a, "s2": p_b})
        print("identical pair score:", identical_rows[0]["score"])
        assert identical_rows[0]["score"] > 0.9, "identical files should score ~1.0"
        assert "<mark" in identical_rows[0]["match_regions_json"]["html_code_a"], (
            "matched regions should be highlighted in the returned HTML"
        )

        unrelated_rows = compare_all_students({"s1": p_a, "s3": p_c})
        print("unrelated pair score:", unrelated_rows[0]["score"])
        assert unrelated_rows[0]["score"] < 0.5, "unrelated files should score low"

        print("similarity_service smoke test passed")
