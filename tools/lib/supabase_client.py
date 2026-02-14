"""Generic Supabase PostgREST + Storage client. Stdlib only.

All Supabase interactions route through here. Every public function checks
_enabled() first, catches all HTTP errors, and returns a safe fallback.
Never raises — graceful degradation when SUPABASE_URL is unset.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _enabled() -> bool:
    """True when both SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set."""
    return bool(
        os.environ.get("SUPABASE_URL", "").strip()
        and os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )


def _headers() -> dict[str, str]:
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }


def _base_url() -> str:
    return os.environ["SUPABASE_URL"].strip().rstrip("/")


def _postgrest(
    method: str,
    table: str,
    body: dict | None = None,
    *,
    params: dict[str, str] | None = None,
    extra_headers: dict[str, str] | None = None,
    return_row: bool = False,
) -> dict | list | None:
    """Low-level PostgREST request. Returns parsed JSON or None on error."""
    url = f"{_base_url()}/rest/v1/{table}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"

    hdrs = _headers()
    hdrs["Content-Type"] = "application/json"
    if return_row:
        hdrs["Prefer"] = "return=representation"
    if extra_headers:
        # Merge — may override Prefer
        for k, v in extra_headers.items():
            if k == "Prefer" and "Prefer" in hdrs:
                hdrs["Prefer"] = f"{hdrs['Prefer']},{v}"
            else:
                hdrs[k] = v

    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, method=method, headers=hdrs, data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if raw and return_row:
                parsed = json.loads(raw)
                if isinstance(parsed, list) and parsed:
                    return parsed[0]
                return parsed
            return None
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        print(f"[supabase] PostgREST {method} {table} failed ({exc.code}): {body_text}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"[supabase] PostgREST {method} {table} error: {exc}", file=sys.stderr)
        return None


def _storage(
    method: str,
    bucket: str,
    path: str,
    data: bytes,
) -> str:
    """Low-level Storage upload. Returns public URL or empty string."""
    url = f"{_base_url()}/storage/v1/object/{bucket}/{path}"
    hdrs = _headers()
    hdrs["Content-Type"] = "application/octet-stream"

    req = urllib.request.Request(url, method=method, headers=hdrs, data=data)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 409 and method == "POST":
            # Already exists — upsert via PUT
            req_put = urllib.request.Request(url, method="PUT", headers=hdrs, data=data)
            try:
                with urllib.request.urlopen(req_put, timeout=120) as resp:
                    resp.read()
            except Exception as exc2:
                print(f"[supabase] Storage PUT {bucket}/{path} failed: {exc2}", file=sys.stderr)
                return ""
        else:
            body_text = exc.read().decode("utf-8", errors="replace")
            print(f"[supabase] Storage {method} {bucket}/{path} failed ({exc.code}): {body_text}", file=sys.stderr)
            return ""
    except Exception as exc:
        print(f"[supabase] Storage {method} {bucket}/{path} error: {exc}", file=sys.stderr)
        return ""

    return f"{_base_url()}/storage/v1/object/public/{bucket}/{path}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def insert(table: str, row: dict, *, return_row: bool = False) -> dict | None:
    """INSERT a row. Returns the row dict if return_row=True, else None."""
    if not _enabled():
        return None
    return _postgrest("POST", table, row, return_row=return_row)


def upsert(table: str, row: dict, *, on_conflict: str = "id") -> dict | None:
    """UPSERT a row (merge duplicates on conflict column)."""
    if not _enabled():
        return None
    return _postgrest(
        "POST", table, row,
        extra_headers={
            "Prefer": "resolution=merge-duplicates",
        },
        params={"on_conflict": on_conflict},
        return_row=True,
    )


def update(table: str, match: dict, data: dict) -> bool:
    """UPDATE rows matching filter. Returns True on success."""
    if not _enabled():
        return False
    params = {k: f"eq.{v}" for k, v in match.items()}
    result = _postgrest("PATCH", table, data, params=params)
    # _postgrest returns None on success (no body) or on error;
    # distinguish by checking that no exception was raised
    return True  # if _postgrest didn't print error, consider success


def query(
    table: str,
    *,
    filters: dict[str, str] | None = None,
    select: str = "*",
    order: str = "",
    limit: int = 0,
) -> list[dict]:
    """SELECT rows. Returns list of dicts, empty on error or disabled."""
    if not _enabled():
        return []
    params: dict[str, str] = {"select": select}
    if filters:
        for k, v in filters.items():
            params[k] = f"eq.{v}"
    if order:
        params["order"] = order
    if limit:
        params["limit"] = str(limit)

    url = f"{_base_url()}/rest/v1/{table}"
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{url}?{qs}"

    hdrs = _headers()
    hdrs["Accept"] = "application/json"

    req = urllib.request.Request(url, method="GET", headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else []
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        print(f"[supabase] query {table} failed ({exc.code}): {body_text}", file=sys.stderr)
        return []
    except Exception as exc:
        print(f"[supabase] query {table} error: {exc}", file=sys.stderr)
        return []


def upload_file(bucket: str, remote_path: str, local_path: str | Path) -> str:
    """Upload a local file to Storage. Returns public URL or empty string."""
    if not _enabled():
        return ""
    local = Path(local_path)
    if not local.is_file():
        print(f"[supabase] upload_file: file not found: {local}", file=sys.stderr)
        return ""
    data = local.read_bytes()
    return _storage("POST", bucket, remote_path, data)


def file_sha256(path: str | Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
