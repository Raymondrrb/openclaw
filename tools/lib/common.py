"""Shared utilities for pipeline tools."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List


def project_root() -> Path:
    """Resolve the project root directory."""
    return Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent.parent))


def now_iso() -> str:
    """UTC timestamp in ISO 8601 format with Z suffix."""
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_iso() -> str:
    """Today's date as YYYY-MM-DD."""
    return dt.date.today().isoformat()


def load_json(path: str, default: Any = None) -> Any:
    """Load a JSON file, returning default if missing or invalid."""
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any) -> None:
    """Write data as formatted JSON (atomic: tmp + fsync + replace)."""
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, json.dumps(data, indent=2).encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def load_jsonl(path: str, limit: int = 0) -> List[Dict[str, Any]]:
    """Load a JSONL file, optionally returning only the last N rows."""
    if not os.path.exists(path):
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if limit > 0:
        return rows[-limit:]
    return rows


def load_env_file(path: str) -> None:
    """Load KEY=VALUE pairs from a file into os.environ (does not overwrite existing)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw or raw.startswith("#") or "=" not in raw:
                    continue
                key, value = raw.split("=", 1)
                key = key.strip()
                if key and key not in os.environ:
                    v = value.strip()
                    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                        v = v[1:-1]
                    os.environ[key] = v
    except OSError:
        return


def ensure_control_plane_url(default_url: str = "https://new-project-control-plane.vercel.app") -> str:
    """Ensure CONTROL_PLANE_URL is populated from known env candidates.

    Accepts values coming from local env exports or Vercel env dumps where
    placeholders like `""` may appear.
    """
    current = _normalize_url_like(os.environ.get("CONTROL_PLANE_URL", ""))
    if current:
        os.environ["CONTROL_PLANE_URL"] = current
        return current

    for candidate in (
        os.environ.get("NEWPROJECT_VERCEL_BASE_URL", ""),
        os.environ.get("VERCEL_URL", ""),
        default_url,
    ):
        normalized = _normalize_url_like(candidate)
        if normalized:
            os.environ["CONTROL_PLANE_URL"] = normalized
            return normalized
    return ""


def _normalize_url_like(value: str) -> str:
    raw = str(value or "").strip().strip("\"'").strip()
    if not raw:
        return ""
    if raw.lower() in {"none", "null", "nil"}:
        return ""
    if raw.startswith(("http://", "https://")):
        return raw.rstrip("/")
    if "." not in raw:
        return ""
    return f"https://{raw}".rstrip("/")


def require_env(name: str) -> str:
    """Get a required environment variable or raise RuntimeError."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def slugify(value: str, max_len: int = 56) -> str:
    """Convert a string to a URL/filesystem-safe slug."""
    import re

    out = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    out = re.sub(r"_+", "_", out)
    return (out[:max_len] or "value").strip("_")


def iso8601_duration_to_seconds(duration: str) -> int:
    """Parse an ISO 8601 duration string (PT#H#M#S) to total seconds."""
    hours = minutes = seconds = 0
    num = ""
    for ch in duration:
        if ch.isdigit():
            num += ch
        elif ch == "H":
            hours = int(num or 0)
            num = ""
        elif ch == "M":
            minutes = int(num or 0)
            num = ""
        elif ch == "S":
            seconds = int(num or 0)
            num = ""
    return hours * 3600 + minutes * 60 + seconds
