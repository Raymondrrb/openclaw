"""Supabase Storage upload and generation logging via PostgREST. Stdlib only."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from tools.lib.common import now_iso, require_env


def _supabase_headers() -> dict[str, str]:
    key = require_env("SUPABASE_SERVICE_ROLE_KEY")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }


def validate_supabase_config() -> None:
    """Raise if required Supabase env vars are missing."""
    require_env("SUPABASE_URL")
    require_env("SUPABASE_SERVICE_ROLE_KEY")


def upload_to_storage(local_path: str | Path, remote_name: str) -> str:
    """Upload a file to Supabase Storage and return the public URL.

    Uses the Storage v1 REST API.
    """
    base_url = require_env("SUPABASE_URL").rstrip("/")
    bucket = os.environ.get("DZINE_STORAGE_BUCKET", "dzine-assets")
    headers = _supabase_headers()
    headers["Content-Type"] = "application/octet-stream"

    local = Path(local_path)
    if not local.is_file():
        raise FileNotFoundError(f"File not found: {local}")

    data = local.read_bytes()
    url = f"{base_url}/storage/v1/object/{bucket}/{remote_name}"

    req = urllib.request.Request(url, method="POST", headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        # 409 = already exists — try upsert via PUT
        if exc.code == 409:
            req_put = urllib.request.Request(url, method="PUT", headers=headers, data=data)
            with urllib.request.urlopen(req_put, timeout=120) as resp:
                resp.read()
        else:
            raise RuntimeError(f"Storage upload failed ({exc.code}): {body}") from exc

    public_url = f"{base_url}/storage/v1/object/public/{bucket}/{remote_name}"
    return public_url


def log_generation(
    *,
    asset_type: str,
    product_name: str,
    style: str,
    status: str,
    local_path: str,
    storage_url: str = "",
    checksum_sha256: str = "",
    duration_s: float = 0.0,
    error: str = "",
    prompt_character: str = "",
    prompt_scene: str = "",
    width: int = 0,
    height: int = 0,
) -> None:
    """Insert a row into dzine_generations via PostgREST."""
    base_url = require_env("SUPABASE_URL").rstrip("/")
    headers = _supabase_headers()
    headers["Content-Type"] = "application/json"
    headers["Prefer"] = "return=minimal"

    row = {
        "asset_type": asset_type,
        "product_name": product_name,
        "style": style,
        "status": status,
        "local_path": local_path,
        "storage_url": storage_url,
        "checksum_sha256": checksum_sha256,
        "duration_s": round(duration_s, 2),
        "error": error[:1000] if error else "",
        "prompt_character": prompt_character,
        "prompt_scene": prompt_scene,
        "width": width,
        "height": height,
        "created_at": now_iso(),
    }

    url = f"{base_url}/rest/v1/dzine_generations"
    payload = json.dumps(row).encode()
    req = urllib.request.Request(url, method="POST", headers=headers, data=payload)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"[supabase] Failed to log generation ({exc.code}): {body}", file=sys.stderr)


def file_sha256(path: str | Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
