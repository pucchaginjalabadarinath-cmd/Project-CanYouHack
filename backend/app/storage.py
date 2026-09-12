"""
File storage wrapper. Per ISSUES.md #5: two dumb I/O functions, no business
logic (file-type validation etc. belongs in the router that calls this, per
FILE_WORKING_GUIDE.md).

Two backends, picked automatically:
  - Supabase Storage, if SUPABASE_URL + SUPABASE_SECRET_KEY are set (see
    backend/.env.example). Uses the raw Storage REST API via urllib
    (stdlib only - no new dependency) rather than a Supabase SDK, since we
    only need two calls (upload object / read object) and the secret key
    is enough to bypass RLS for both.
  - Local disk fallback otherwise, under LOCAL_STORAGE_ROOT. This is what
    lets `download_file(upload_file(...))` be tested (and the assignment
    PDF / submission upload flow to work end to end) before a real
    Supabase project + bucket exist - per HANDOFF.md, DB password/secret
    key are still placeholders as of this session.

Both backends return a URL that download_file() can turn back into the
original bytes - callers (routers, services) never need to know which
backend produced it.
"""

import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

_USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_SECRET_KEY)

# Kept out of the repo (see .gitignore) - each bucket/path pair lives under
# here as an actual file on disk when running without real Supabase creds.
LOCAL_STORAGE_ROOT = Path(
    os.environ.get(
        "LOCAL_STORAGE_ROOT", Path(__file__).resolve().parent.parent / "local_storage"
    )
)


def upload_file(bucket: str, path: str, file_bytes: bytes) -> str:
    """
    Uploads `file_bytes` to `bucket/path` and returns a URL that
    `download_file` can later use to read the same bytes back.
    """
    if _USE_SUPABASE:
        return _upload_supabase(bucket, path, file_bytes)
    return _upload_local(bucket, path, file_bytes)


def download_file(url: str) -> bytes:
    """
    Reads back whatever `upload_file` produced a URL for, regardless of
    which backend produced it (checked via the URL scheme/shape).
    """
    if url.startswith("file://"):
        return _download_local(url)
    return _download_http(url)


# ---------------------------------------------------------------------------
# Supabase Storage backend
# ---------------------------------------------------------------------------


def _upload_supabase(bucket: str, path: str, file_bytes: bytes) -> str:
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{quote(path)}"

    request = urllib.request.Request(
        upload_url,
        data=file_bytes,
        method="POST",
        headers={
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "apikey": SUPABASE_SECRET_KEY,
            "Content-Type": content_type,
            # Lets a retry/re-upload to the same path overwrite instead of
            # 409-ing - useful for e.g. re-uploading a corrected AI
            # reference solution to the same question.
            "x-upsert": "true",
        },
    )
    try:
        with urllib.request.urlopen(request) as response:
            response.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"Supabase Storage upload failed ({e.code}): {e.read().decode(errors='replace')}"
        ) from e

    # Assumes the bucket is public (fine for a hackathon - PDFs and code
    # submissions aren't secret to anyone with the link). Swap for the
    # signed-URL endpoint here if a bucket needs to stay private later;
    # callers don't need to change since they only ever see a URL string.
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{quote(path)}"


def _download_http(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers=(
            {"Authorization": f"Bearer {SUPABASE_SECRET_KEY}", "apikey": SUPABASE_SECRET_KEY}
            if _USE_SUPABASE and url.startswith(str(SUPABASE_URL))
            else {}
        ),
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"download_file failed ({e.code}) for {url}") from e


# ---------------------------------------------------------------------------
# Local disk fallback
# ---------------------------------------------------------------------------


def _local_path(bucket: str, path: str) -> Path:
    # `path` may itself contain slashes (e.g. "question-id/filename.c") -
    # that's fine, it just becomes nested directories under the bucket.
    return LOCAL_STORAGE_ROOT / bucket / path


def _upload_local(bucket: str, path: str, file_bytes: bytes) -> str:
    full_path = _local_path(bucket, path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(file_bytes)
    return f"file://{full_path.resolve()}"


def _download_local(url: str) -> bytes:
    local_path = Path(url[len("file://") :])
    return local_path.read_bytes()
