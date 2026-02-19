"""Shared I/O utilities for the rayvault package."""

from __future__ import annotations

import hashlib
import json
import os
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def atomic_write_json(path: Path, data: Any, indent: int = 2) -> None:
    """Write JSON atomically: mkdir + tmp + fsync + os.replace.

    Ensures data reaches disk before the target file is visible,
    preventing corrupt reads on crash or power-loss.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, indent=indent, ensure_ascii=False).encode("utf-8")
    payload += b"\n"
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))


def utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string (YYYY-MM-DDTHH:MM:SSZ)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> Dict[str, Any]:
    """Read a JSON file and return parsed contents."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sha1_file(path: Path) -> str:
    """Compute SHA-1 hex digest of a file (1 MB chunks)."""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha1_text(s: str) -> str:
    """Compute SHA-1 hex digest of a UTF-8 string."""
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def wav_duration_seconds(path: Path) -> Optional[float]:
    """Read WAV duration via wave module. Returns None if unreadable."""
    if not path.exists():
        return None
    try:
        with wave.open(str(path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            if rate <= 0:
                return None
            return frames / float(rate)
    except Exception:
        return None
