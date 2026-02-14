#!/usr/bin/env python3
"""RayVault Amazon Quarantine — cooldown lock after 403/429 blocks.

Prevents hammering Amazon after receiving rate-limit or ban responses.
All runs check the quarantine lock before making any Amazon HTTP request.

Lock file format (state/amazon_quarantine.lock):
    {"at_utc": "...", "code": 429, "cooldown_until_utc": "...", "note": "..."}

Usage:
    from rayvault.amazon_quarantine import is_quarantined, set_quarantine, remaining_minutes

    if is_quarantined(lock_path):
        # skip Amazon calls, use survival mode
        ...

    # On 403/429:
    set_quarantine(lock_path, code=429, cooldown_hours=4.0)
"""

from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def _parse_utc(iso_str: str) -> Optional[float]:
    """Parse ISO UTC string to timestamp. Returns None on failure."""
    try:
        return datetime.fromisoformat(
            iso_str.replace("Z", "+00:00")
        ).timestamp()
    except Exception:
        return None


def is_quarantined(lock_path: Path, cooldown_hours: float = 4.0) -> bool:
    """Check if Amazon quarantine is currently active.

    Uses cooldown_until_utc if present in lock file,
    otherwise falls back to file mtime + cooldown_hours.
    """
    if not lock_path.exists():
        return False
    try:
        data = _read_json(lock_path)
        until = data.get("cooldown_until_utc")
        if until:
            ts = _parse_utc(until)
            if ts:
                return time.time() < ts
        # Fallback: mtime + cooldown
        age_h = (time.time() - lock_path.stat().st_mtime) / 3600.0
        return age_h < cooldown_hours
    except Exception:
        # Corrupted lock: fail-safe active for 1h from mtime
        try:
            age_h = (time.time() - lock_path.stat().st_mtime) / 3600.0
            return age_h < 1.0
        except Exception:
            return False


def set_quarantine(
    lock_path: Path,
    code: int,
    cooldown_hours: float = 4.0,
    jitter_minutes: int = 30,
    note: str = "auto quarantine",
) -> None:
    """Set Amazon quarantine lock with cooldown + jitter."""
    jitter_h = random.uniform(0, max(0, jitter_minutes)) / 60.0
    total_h = max(0.1, cooldown_hours + jitter_h)
    until_dt = datetime.now(timezone.utc) + timedelta(hours=total_h)
    payload = {
        "at_utc": utc_now_iso(),
        "code": int(code),
        "note": note,
        "cooldown_hours": float(cooldown_hours),
        "cooldown_until_utc": until_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _atomic_write_json(lock_path, payload)


def remaining_minutes(lock_path: Path) -> int:
    """Get remaining quarantine minutes. Returns 0 if not active."""
    if not lock_path.exists():
        return 0
    try:
        data = _read_json(lock_path)
        until = data.get("cooldown_until_utc")
        if not until:
            return 0
        ts = _parse_utc(until)
        if not ts:
            return 0
        delta_sec = ts - time.time()
        return max(0, int(delta_sec // 60))
    except Exception:
        return 0


def clear_quarantine(lock_path: Path) -> bool:
    """Manually clear quarantine lock."""
    try:
        if lock_path.exists():
            lock_path.unlink()
            return True
    except OSError:
        pass
    return False
