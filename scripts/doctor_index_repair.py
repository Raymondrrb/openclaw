#!/usr/bin/env python3
"""RayVault Dangling Index Repair — detect and quarantine stale index entries.

Definitions:
  - "Dangling" = index entry whose file no longer exists on disk
  - Separate from orphans (file exists but not in index)

Dangling reasons (classified for operator action):
  - missing_path:     entry has no "path" field at all
  - missing_file:     path resolves but file doesn't exist (double-checked)
  - permission_denied: file exists but stat() fails (env problem, don't touch)
  - outside_root:     path resolves outside state_root (suspicious/stale)

Strategy:
  - Default: dry-run — marks entries with dangling=True (no removal)
  - --apply: moves dangling entries to idx["dangling_items"] bucket
  - --apply --delete: removes dangling entries entirely (no bucket)
  - Uses advisory file lock (same as video_index_refresh)
  - Resolves relative paths via state_root (reduces false positives)
  - Double-checks missing_file with 0.5s sleep (filesystem flicker guard)
  - repair_history ring buffer with env fingerprint in meta_info

Usage:
    python3 scripts/doctor_index_repair.py --state-dir state
    python3 scripts/doctor_index_repair.py --state-dir state --apply
    python3 scripts/doctor_index_repair.py --state-dir state --apply --delete

Exit codes:
    0: OK
    1: Dangling entries found (dry-run)
    2: Error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_STATE_DIR = Path("state")
DEFAULT_INDEX_PATH = DEFAULT_STATE_DIR / "video" / "index.json"


# ---------------------------------------------------------------------------
# Atomic JSON I/O
# ---------------------------------------------------------------------------

def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically: write to .tmp, fsync, os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _load_index(index_path: Path) -> dict:
    """Load video index. Returns empty structure on missing/corrupt."""
    if not index_path.exists():
        return {"version": "1.0", "items": {}}
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": "1.0", "items": {}}


# ---------------------------------------------------------------------------
# File lock (same as video_index_refresh)
# ---------------------------------------------------------------------------

@contextmanager
def _index_lock(index_path: Path, timeout: float = 10.0):
    """Advisory file lock to prevent concurrent index corruption."""
    lock_path = index_path.with_suffix(".json.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl
    except ImportError:
        yield
        return

    fd = open(lock_path, "w")
    try:
        start = time.monotonic()
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError):
                if time.monotonic() - start >= timeout:
                    fd.close()
                    raise TimeoutError(
                        f"Could not acquire index lock within {timeout}s"
                    )
                time.sleep(0.5)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except Exception:
            pass
        fd.close()


# ---------------------------------------------------------------------------
# Root guard
# ---------------------------------------------------------------------------

def _is_under_root(p: Path, root: Path) -> bool:
    """Check if resolved path is under root directory."""
    try:
        p.expanduser().resolve().relative_to(root.expanduser().resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Environment fingerprint
# ---------------------------------------------------------------------------

def _env_fingerprint() -> Dict[str, str]:
    """Minimal environment fingerprint for history entries."""
    try:
        from _env_fingerprint import env_fingerprint
        return env_fingerprint()
    except ImportError:
        import platform
        return {
            "hostname": platform.node() or "unknown",
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "platform": sys.platform,
            "cwd": os.getcwd(),
        }


# ---------------------------------------------------------------------------
# Repair logic
# ---------------------------------------------------------------------------

def _is_valid_path_value(raw_path: str) -> bool:
    """Check if raw_path is a semantically valid path (not junk)."""
    if not raw_path or not raw_path.strip():
        return False
    stripped = raw_path.strip()
    # Reject obviously broken values
    if stripped in (".", "/", "..", "//", "None", "null", "undefined"):
        return False
    return True


def repair_dangling(
    index_path: Path = DEFAULT_INDEX_PATH,
    apply: bool = False,
    move_to_bucket: bool = True,
    double_check_sleep: float = 0.5,
) -> Dict[str, Any]:
    """Detect and handle dangling index entries.

    Classification of dangling reasons:
      - missing_path:       entry has no "path" field at all
      - invalid_path_value: path field is junk (".", "/", empty string, etc.)
      - missing_file:       path resolves but file doesn't exist (double-checked)
      - permission_denied:  file may exist but stat() fails (env problem, don't touch)
      - outside_root:       path resolves outside state_root (suspicious)
      - storage_unavailable: state_root itself is inaccessible (abort repair)

    Persistence tracking:
      - dangling_seen_count: incremented on each scan where item is still dangling
      - dangling_last_seen_at: timestamp of most recent detection
      - Items only become bucket-eligible after seen_count >= threshold

    Args:
        index_path: Path to index.json.
        apply: If True, remove dangling entries from items.
        move_to_bucket: If True (and apply), move to dangling_items bucket.
        double_check_sleep: Seconds to wait before second existence check.

    Returns:
        Dict with repair stats.
    """
    now = datetime.now(timezone.utc).isoformat()
    stats: Dict[str, Any] = {
        "checked": 0,
        "dangling_found": 0,
        "dangling_missing_path": 0,
        "dangling_invalid_path": 0,
        "dangling_missing_file": 0,
        "dangling_permission_denied": 0,
        "dangling_outside_root": 0,
        "storage_unavailable": False,
        "apply": apply,
        "entries": [],
    }

    with _index_lock(index_path):
        idx = _load_index(index_path)
        items = idx.get("items", {})
        meta_info = idx.setdefault("meta_info", {})

        # Seal state_root if not present
        state_root = index_path.parent.parent.resolve()
        declared_root = meta_info.get("state_root")
        if declared_root:
            state_root = Path(declared_root).resolve()
        else:
            meta_info["state_root"] = str(state_root)

        # Storage guard: if state_root is inaccessible, abort
        try:
            if not state_root.exists():
                stats["storage_unavailable"] = True
                _persist_repair_history(meta_info, stats, now, apply, move_to_bucket)
                _atomic_write_json(index_path, idx)
                return stats
        except (PermissionError, OSError):
            stats["storage_unavailable"] = True
            _persist_repair_history(meta_info, stats, now, apply, move_to_bucket)
            _atomic_write_json(index_path, idx)
            return stats

        keys_to_remove: List[str] = []

        for sha8, meta in list(items.items()):
            if not isinstance(meta, dict):
                continue
            stats["checked"] += 1

            raw_path = meta.get("path")
            reason = None

            if raw_path is None:
                reason = "missing_path"
                stats["dangling_missing_path"] += 1
            elif not _is_valid_path_value(raw_path):
                reason = "invalid_path_value"
                stats["dangling_invalid_path"] += 1
            else:
                p = Path(raw_path).expanduser()
                # Resolve relative paths via state_root
                if not p.is_absolute():
                    p = state_root / p
                path = p.resolve()

                # Guard: reject paths that escape root after resolve
                if not _is_under_root(path, state_root):
                    reason = "outside_root"
                    stats["dangling_outside_root"] += 1
                else:
                    # Check existence with permission awareness
                    try:
                        exists = path.exists()
                    except PermissionError:
                        reason = "permission_denied"
                        stats["dangling_permission_denied"] += 1

                    if reason is None and not exists:
                        # Double-check: filesystem may flicker (mount, sync, sleep)
                        time.sleep(double_check_sleep)
                        try:
                            exists = path.exists()
                        except PermissionError:
                            reason = "permission_denied"
                            stats["dangling_permission_denied"] += 1
                        if reason is None and not exists:
                            reason = "missing_file"
                            stats["dangling_missing_file"] += 1

            if reason is None:
                # File is healthy — clear any previous dangling flags
                if meta.get("dangling"):
                    meta.pop("dangling", None)
                    meta.pop("dangling_reason", None)
                    meta.pop("dangling_at", None)
                    meta.pop("dangling_seen_count", None)
                    meta.pop("dangling_last_seen_at", None)
                continue

            # Track persistence: increment seen_count
            prev_count = meta.get("dangling_seen_count", 0)
            meta["dangling"] = True
            meta["dangling_reason"] = reason
            meta["dangling_last_seen_at"] = now
            meta["dangling_seen_count"] = prev_count + 1
            if "dangling_at" not in meta:
                meta["dangling_at"] = now

            # permission_denied is informational — never remove
            if reason == "permission_denied":
                stats["dangling_found"] += 1
                stats["entries"].append((sha8, reason))
                continue

            stats["dangling_found"] += 1
            stats["entries"].append((sha8, reason))

            if apply:
                if move_to_bucket:
                    bucket = idx.setdefault("dangling_items", {})
                    bucket[sha8] = {
                        **meta,
                        "dangling_reason": reason,
                        "dangling_at": meta.get("dangling_at", now),
                        "dangling_seen_count": meta["dangling_seen_count"],
                    }
                keys_to_remove.append(sha8)

        # Remove after iteration
        for k in keys_to_remove:
            items.pop(k, None)

        _persist_repair_history(meta_info, stats, now, apply, move_to_bucket)
        _atomic_write_json(index_path, idx)

    return stats


def _persist_repair_history(
    meta_info: dict,
    stats: Dict[str, Any],
    now: str,
    apply: bool,
    move_to_bucket: bool = True,
) -> None:
    """Append to repair_history ring buffer."""
    history = meta_info.get("repair_history", [])
    history.append({
        "at": now,
        "checked": stats["checked"],
        "dangling_found": stats["dangling_found"],
        "dangling_missing_path": stats["dangling_missing_path"],
        "dangling_invalid_path": stats.get("dangling_invalid_path", 0),
        "dangling_missing_file": stats["dangling_missing_file"],
        "dangling_permission_denied": stats["dangling_permission_denied"],
        "dangling_outside_root": stats["dangling_outside_root"],
        "storage_unavailable": stats["storage_unavailable"],
        "apply": apply,
        "mode": "move_to_bucket" if move_to_bucket else "delete",
        "env": _env_fingerprint(),
    })
    meta_info["repair_history"] = history[-10:]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RayVault Dangling Index Repair (detect stale entries)",
    )
    parser.add_argument("--state-dir", default="state")
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually remove dangling entries from items",
    )
    parser.add_argument(
        "--delete", action="store_true",
        help="Delete entries instead of moving to dangling_items bucket",
    )
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir)
    index_path = state_dir / "video" / "index.json"

    print("RayVault Dangling Index Repair")
    print(f"  index: {index_path}")
    print(f"  mode: {'APPLY' if args.apply else 'DRY-RUN'}"
          f"{' (delete)' if args.delete else ' (bucket)' if args.apply else ''}")

    stats = repair_dangling(
        index_path=index_path,
        apply=args.apply,
        move_to_bucket=not args.delete,
    )

    if stats["storage_unavailable"]:
        print("\n  ABORT: state_root is inaccessible (storage_unavailable)")
        print("  Check mounts, drives, and permissions before running repair.")
        return 2

    print(f"\n  Checked: {stats['checked']}")
    print(f"  Dangling found: {stats['dangling_found']}")
    if stats["dangling_missing_path"] > 0:
        print(f"    missing_path: {stats['dangling_missing_path']}")
    if stats["dangling_invalid_path"] > 0:
        print(f"    invalid_path_value: {stats['dangling_invalid_path']}")
    if stats["dangling_missing_file"] > 0:
        print(f"    missing_file: {stats['dangling_missing_file']}")
    if stats["dangling_permission_denied"] > 0:
        print(f"    permission_denied: {stats['dangling_permission_denied']} (not removed)")
    if stats["dangling_outside_root"] > 0:
        print(f"    outside_root: {stats['dangling_outside_root']}")

    if stats["entries"]:
        print("\n  Dangling entries:")
        for sha8, reason in stats["entries"][:10]:
            print(f"    - {sha8}: {reason}")
        if len(stats["entries"]) > 10:
            print(f"    ... ({len(stats['entries']) - 10} more)")

    if not args.apply and stats["dangling_found"] > 0:
        print("\n  DRY-RUN: entries marked but not removed.")
        print("  To apply: use --apply")
        print("  To delete (no bucket): use --apply --delete")

    return 1 if stats["dangling_found"] > 0 and not args.apply else 0


if __name__ == "__main__":
    sys.exit(main())
