"""
File storage - thin I/O wrapper, per ISSUES.md #5 and FILE_WORKING_GUIDE.md
("two functions, both dumb wrappers... keep this file a thin I/O layer").

Two functions, used by both the assignment-PDF upload and the student
submission upload:
    upload_file(bucket, path, file_bytes) -> url
    download_file(url) -> bytes

No business logic here (file-type/size validation belongs in the router
that calls this, per FILE_WORKING_GUIDE.md) - this file only knows how to
move bytes in and out of storage.

Backend: Supabase Storage (free tier, 1GB - see RESOURCES.md), using the
`supabase` Python client with the server-side secret key so uploads bypass
RLS (never expose that key to the frontend - it lives only in
backend/.env, same pattern as SUPABASE_URL in auth.py).

Local disk fallback: per ISSUES.md #5's "(or local disk fallback)", if
Supabase Storage env vars aren't set yet this falls back to writing under
STORAGE_LOCAL_DIR (default ./local_storage) and returns a `file://` URL.
This lets routers/assignments.py and routers/submissions.py be built and
smoke-tested before the real Supabase project + storage buckets exist,
without silently pointing at Supabase in a broken/half-configured state -
Supabase mode only turns on once BOTH SUPABASE_URL and
SUPABASE_SECRET_KEY are present.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")
STORAGE_LOCAL_DIR = os.environ.get("STORAGE_LOCAL_DIR", "./local_storage")

_USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_SECRET_KEY)

# Matches the public-object URL shape Supabase's get_public_url() returns:
# {SUPABASE_URL}/storage/v1/object/public/{bucket}/{path...}
_SUPABASE_PUBLIC_URL_RE = re.compile(r"/storage/v1/object/public/([^/]+)/(.+)$")

_client = None  # lazily created - see _get_client()


def _get_client():
    """Creates the Supabase client once and reuses it (mirrors auth.py's
    module-level PyJWKClient pattern - one client, not one per call)."""
    global _client
    if _client is None:
        from supabase import create_client  # imported lazily so local-disk
        # mode (used before Supabase is set up) doesn't require the
        # `supabase` package to even be importable yet.
        _client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
    return _client


def _local_path_for(bucket: str, path: str) -> Path:
    return Path(STORAGE_LOCAL_DIR) / bucket / path


def upload_file(bucket: str, path: str, file_bytes: bytes) -> str:
    """Uploads `file_bytes` to `bucket`/`path` and returns a URL that
    `download_file` can read back byte-identical.

    `path` should already include any filename/extension the caller wants
    preserved (e.g. "assignment-42/reference.c") - this function doesn't
    generate or sanitize names.
    """
    if _USE_SUPABASE:
        client = _get_client()
        client.storage.from_(bucket).upload(
            path,
            file_bytes,
            {"upsert": "true"},
        )
        return client.storage.from_(bucket).get_public_url(path)

    local_path = _local_path_for(bucket, path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(file_bytes)
    return f"file://{local_path.resolve()}"


def download_file(url: str) -> bytes:
    """Reads back whatever `upload_file` wrote, given the URL it returned.

    Handles both URL shapes upload_file can produce:
      - `file://...` (local-disk fallback mode)
      - a Supabase public storage URL (Supabase mode) - bucket/path are
        parsed back out of the URL rather than requiring the caller to
        track them separately, since `Submission.file_url` /
        `Question.ai_reference_url` in models.py only store the URL.
    """
    if url.startswith("file://"):
        return Path(url[len("file://"):]).read_bytes()

    match = _SUPABASE_PUBLIC_URL_RE.search(url)
    if not match:
        raise ValueError(f"don't know how to download from this url: {url}")
    bucket, path = match.group(1), match.group(2)
    return _get_client().storage.from_(bucket).download(path)


if __name__ == "__main__":
    # Standalone smoke test per ISSUES.md #5's acceptance criteria:
    # "uploading a small .txt file returns a URL that download_file can
    # read back byte-identical." Runs in local-disk fallback mode (no
    # Supabase env vars needed) so it works in any environment. Run with:
    #   python -m app.storage
    import shutil
    import tempfile

    test_dir = tempfile.mkdtemp()
    os.environ["STORAGE_LOCAL_DIR"] = test_dir
    STORAGE_LOCAL_DIR = test_dir  # noqa: F811 - re-bind for this test run

    try:
        original = b"hello from the storage smoke test\n"
        url = upload_file("test-bucket", "smoke/test.txt", original)
        print("uploaded to:", url)
        assert url.startswith("file://"), "expected local-disk fallback URL"

        round_tripped = download_file(url)
        assert round_tripped == original, "downloaded bytes must match exactly"
        print("storage.py smoke test passed (local-disk mode)")
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
