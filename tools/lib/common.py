"""Shared utilities for Python tools. Stdlib only — no external deps."""

from __future__ import annotations

import datetime
import os
from pathlib import Path


def project_root() -> Path:
    """Return the repository root (two levels up from tools/lib/)."""
    return Path(__file__).resolve().parent.parent.parent


def load_env_file(path: str | Path | None = None) -> None:
    """Read a KEY=VALUE env file and inject into os.environ (does not override)."""
    if path is None:
        path = project_root() / ".env"
    path = Path(path)
    if not path.is_file():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value


def require_env(name: str) -> str:
    """Return an env var or raise with a helpful message."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise EnvironmentError(f"Required environment variable {name!r} is not set")
    return value


def now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
