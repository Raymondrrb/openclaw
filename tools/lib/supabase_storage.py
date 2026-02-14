"""Supabase Storage — thin shim over supabase_client.

Preserves backward compat for dzine_gen.py and dzine_browser.py.
"""

from __future__ import annotations

from tools.lib.supabase_client import file_sha256, insert as _insert, upload_file
from tools.lib.supabase_client import _enabled


def validate_supabase_config() -> None:
    """Raise if required Supabase env vars are missing."""
    if not _enabled():
        raise EnvironmentError("Supabase not configured")


def upload_to_storage(local_path, remote_name: str) -> str:
    """Upload a file and return the public URL."""
    bucket = __import__("os").environ.get("DZINE_STORAGE_BUCKET", "dzine-assets")
    return upload_file(bucket, remote_name, local_path)


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
    from tools.lib.common import now_iso
    _insert("dzine_generations", {
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
    })
