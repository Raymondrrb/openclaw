#!/usr/bin/env python3
"""RayVault Dangling Index Resurrect — restore entries from dangling_items bucket.

Closes the reversibility cycle: items -> dangling_items -> items.

An item is resurrected ONLY if ALL of these are true:
  1. The path (resolved via state_root) exists on disk
  2. The path is under state_root (root guard)
  3. The file has sha8 in filename (or --allow-missing-sha8)
  4. No conflict with existing item (same sha8 key already in items)
  5. The file is stable (size hasn't changed in 0.3s)

Strategy:
  - Default: dry-run (report only)
  - --apply: actually restore entries to items
  - --limit N: max entries to restore per run (safety valve)
  - resurrect_history ring buffer in meta_info
  - Uses advisory file lock

Usage:
    python3 scripts/doctor_index_resurrect.py --state-dir state
    python3 scripts/doctor_index_resurrect.py --state-dir state --apply
    python3 scripts/doctor_index_resurrect.py --state-dir state --apply --limit 10
    python3 scripts/doctor_index_resurrect.py --state-dir state --apply --allow-missing-sha8

Exit codes:
    0: OK (or nothing to restore)
    1: Candidates found (dry-run)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


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
# File lock
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
# Helpers
# ---------------------------------------------------------------------------

def _is_under_root(p: Path, root: Path) -> bool:
    """Check if resolved path is under root directory."""
    try:
        p.expanduser().resolve().relative_to(root.expanduser().resolve())
        return True
    except ValueError:
        return False


def _has_sha8_in_filename(p: Path) -> bool:
    """Check if filename contains a sha8 hex suffix."""
    return bool(re.search(r"_([0-9a-fA-F]{8})\.mp4$", p.name))


def _is_file_stable(path: Path, sleep_s: float = 0.3) -> bool:
    """Verify file size hasn't changed (catches mid-write files)."""
    try:
        s1 = path.stat().st_size
        if s1 == 0:
            return False
        time.sleep(sleep_s)
        s2 = path.stat().st_size
        return s1 == s2
    except OSError:
        return False


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
# Resurrect logic
# ---------------------------------------------------------------------------

def resurrect_dangling(
    index_path: Path = DEFAULT_INDEX_PATH,
    apply: bool = False,
    limit: int = 0,
    allow_missing_sha8: bool = False,
) -> Dict[str, Any]:
    """Attempt to restore entries from dangling_items back to items.

    An entry is restored only if ALL validation gates pass:
      1. path exists on disk
      2. path is under state_root
      3. sha8 in filename (or allow_missing_sha8)
      4. no key conflict in items
      5. file is stable

    Args:
        index_path: Path to index.json.
        apply: If True, actually restore entries.
        limit: Max entries to restore (0 = unlimited).
        allow_missing_sha8: Allow restore of entries without sha8.

    Returns:
        Dict with resurrect stats.
    """
    now = datetime.now(timezone.utc).isoformat()
    stats: Dict[str, Any] = {
        "candidates": 0,
        "restored": 0,
        "rejected_missing_file": 0,
        "rejected_outside_root": 0,
        "rejected_no_sha8": 0,
        "rejected_conflict": 0,
        "rejected_unstable": 0,
        "rejected_permission": 0,
        "apply": apply,
        "entries": [],
    }

    with _index_lock(index_path):
        idx = _load_index(index_path)
        items = idx.get("items", {})
        dangling_items = idx.get("dangling_items", {})
        meta_info = idx.setdefault("meta_info", {})

        if not dangling_items:
            # Persist history even when empty (observability)
            _persist_history(meta_info, stats, now, apply)
            _atomic_write_json(index_path, idx)
            return stats

        # Resolve state_root
        state_root = index_path.parent.parent.resolve()
        declared_root = meta_info.get("state_root")
        if declared_root:
            state_root = Path(declared_root).resolve()

        keys_to_restore: List[str] = []
        restored_count = 0

        for sha8, meta in list(dangling_items.items()):
            if not isinstance(meta, dict):
                continue
            stats["candidates"] += 1

            raw_path = meta.get("path")
            if not raw_path:
                stats["rejected_missing_file"] += 1
                stats["entries"].append((sha8, "no_path"))
                continue

            p = Path(raw_path).expanduser()
            if not p.is_absolute():
                p = state_root / p
            path = p.resolve()

            # Gate 1: file exists
            try:
                exists = path.exists()
            except PermissionError:
                stats["rejected_permission"] += 1
                stats["entries"].append((sha8, "permission_denied"))
                continue

            if not exists:
                stats["rejected_missing_file"] += 1
                stats["entries"].append((sha8, "missing_file"))
                continue

            # Gate 2: under root
            if not _is_under_root(path, state_root):
                stats["rejected_outside_root"] += 1
                stats["entries"].append((sha8, "outside_root"))
                continue

            # Gate 3: sha8 in filename
            if not allow_missing_sha8 and not _has_sha8_in_filename(path):
                stats["rejected_no_sha8"] += 1
                stats["entries"].append((sha8, "no_sha8"))
                continue

            # Gate 4: no conflict
            if sha8 in items:
                stats["rejected_conflict"] += 1
                stats["entries"].append((sha8, "conflict"))
                continue

            # Gate 5: file stable
            if not _is_file_stable(path):
                stats["rejected_unstable"] += 1
                stats["entries"].append((sha8, "unstable"))
                continue

            # All gates passed
            if apply:
                if 0 < limit <= restored_count:
                    break
                # Clean up dangling metadata before restoring
                restored_meta = {k: v for k, v in meta.items()
                                 if k not in ("dangling", "dangling_reason", "dangling_at")}
                restored_meta["restored_at"] = now
                items[sha8] = restored_meta
                keys_to_restore.append(sha8)
                restored_count += 1
                stats["restored"] += 1
                stats["entries"].append((sha8, "restored"))
            else:
                stats["entries"].append((sha8, "eligible"))

        # Remove restored entries from bucket
        for k in keys_to_restore:
            dangling_items.pop(k, None)

        # Clean up empty bucket
        if not dangling_items:
            idx.pop("dangling_items", None)

        _persist_history(meta_info, stats, now, apply)
        _atomic_write_json(index_path, idx)

    return stats


def _persist_history(
    meta_info: dict,
    stats: Dict[str, Any],
    now: str,
    apply: bool,
) -> None:
    """Append to resurrect_history ring buffer."""
    history = meta_info.get("resurrect_history", [])
    history.append({
        "at": now,
        "candidates": stats["candidates"],
        "restored": stats["restored"],
        "rejected_missing_file": stats["rejected_missing_file"],
        "rejected_outside_root": stats["rejected_outside_root"],
        "rejected_no_sha8": stats["rejected_no_sha8"],
        "rejected_conflict": stats["rejected_conflict"],
        "rejected_unstable": stats["rejected_unstable"],
        "rejected_permission": stats["rejected_permission"],
        "apply": apply,
        "env": _env_fingerprint(),
    })
    meta_info["resurrect_history"] = history[-10:]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RayVault Dangling Index Resurrect (restore from bucket)",
    )
    parser.add_argument("--state-dir", default="state")
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually restore entries to items",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Max entries to restore per run (0 = unlimited)",
    )
    parser.add_argument(
        "--allow-missing-sha8", action="store_true",
        help="Allow restoring entries without sha8 in filename",
    )
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir)
    index_path = state_dir / "video" / "index.json"

    print("RayVault Dangling Index Resurrect")
    print(f"  index: {index_path}")
    print(f"  mode: {'APPLY' if args.apply else 'DRY-RUN'}"
          f"{f' (limit={args.limit})' if args.limit > 0 else ''}"
          f"{' +allow-missing-sha8' if args.allow_missing_sha8 else ''}")

    stats = resurrect_dangling(
        index_path=index_path,
        apply=args.apply,
        limit=args.limit,
        allow_missing_sha8=args.allow_missing_sha8,
    )

    print(f"\n  Candidates (in bucket): {stats['candidates']}")
    print(f"  Restored: {stats['restored']}")
    if stats["rejected_missing_file"] > 0:
        print(f"  Rejected (missing file): {stats['rejected_missing_file']}")
    if stats["rejected_outside_root"] > 0:
        print(f"  Rejected (outside root): {stats['rejected_outside_root']}")
    if stats["rejected_no_sha8"] > 0:
        print(f"  Rejected (no sha8): {stats['rejected_no_sha8']}")
    if stats["rejected_conflict"] > 0:
        print(f"  Rejected (conflict): {stats['rejected_conflict']}")
    if stats["rejected_unstable"] > 0:
        print(f"  Rejected (unstable): {stats['rejected_unstable']}")
    if stats["rejected_permission"] > 0:
        print(f"  Rejected (permission): {stats['rejected_permission']}")

    eligible = [e for e in stats["entries"] if e[1] in ("eligible", "restored")]
    rejected = [e for e in stats["entries"] if e[1] not in ("eligible", "restored")]

    if eligible:
        label = "Restored" if args.apply else "Eligible for restore"
        print(f"\n  {label}:")
        for sha8, status in eligible[:10]:
            print(f"    - {sha8}: {status}")
        if len(eligible) > 10:
            print(f"    ... ({len(eligible) - 10} more)")

    if rejected:
        print(f"\n  Rejected:")
        for sha8, reason in rejected[:10]:
            print(f"    - {sha8}: {reason}")
        if len(rejected) > 10:
            print(f"    ... ({len(rejected) - 10} more)")

    if not args.apply and eligible:
        print("\n  DRY-RUN: no entries restored.")
        print("  To apply: use --apply")

    return 1 if eligible and not args.apply else 0


if __name__ == "__main__":
    sys.exit(main())
