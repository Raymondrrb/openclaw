#!/usr/bin/env python3
"""RayVault Doctor Cleanup — quarantine-safe orphan management.

Definitions:
  - "Orphan" = .mp4 in final_dir NOT referenced by index.json
  - "Dangling" = index entry whose file no longer exists on disk

Strategy:
  - Default: dry-run (report only, no action)
  - --quarantine: move orphans to quarantine_dir (atomic via os.replace)
  - --delete: permanently delete orphans (requires explicit flag)
  - Never deletes by default — quarantine is the safe path

Filters:
  --older-than-hours N   Only orphans with mtime older than N hours
  --min-size-kb N        Ignore files smaller than N KB (default 500)
  --keep-last-n N        Never touch the N most recent mp4s (safety net)

Usage:
    python3 scripts/doctor_cleanup.py --dry-run
    python3 scripts/doctor_cleanup.py --quarantine
    python3 scripts/doctor_cleanup.py --quarantine --older-than-hours 6
    python3 scripts/doctor_cleanup.py --delete --older-than-hours 48

Exit codes:
    0: OK (or dry-run)
    2: Action failed (move/delete errors) or invalid flags
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_INDEX_PATH = Path("state/video/index.json")
DEFAULT_FINAL_DIR = Path("state/video/final")
DEFAULT_QUARANTINE_DIR = Path("state/video/quarantine")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Orphan:
    path: Path
    size_bytes: int
    mtime_utc: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_index(index_path: Path) -> Dict[str, Any]:
    """Load video index. Raises on corrupt file (never delete if index is bad)."""
    if not index_path.exists():
        return {}
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        raise RuntimeError(f"Index JSON corrupt: {index_path} — refusing to act")


def _index_referenced_filenames(index: Dict[str, Any]) -> set:
    """Extract filenames (not full paths) from index for robust comparison."""
    referenced = set()
    items = index.get("items", index)
    if not isinstance(items, dict):
        return referenced
    for _key, meta in items.items():
        if not isinstance(meta, dict):
            continue
        p = meta.get("path", "")
        if isinstance(p, str) and p.strip():
            referenced.add(Path(p).name)
    return referenced


def _file_mtime_utc(p: Path) -> datetime:
    ts = p.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def human_size(n: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n = n / 1024  # type: ignore[assignment]
    return f"{n:.0f}PB"


# ---------------------------------------------------------------------------
# Orphan detection
# ---------------------------------------------------------------------------

def find_orphans(
    final_dir: Path,
    referenced_filenames: set,
    older_than_hours: Optional[float] = None,
    min_size_kb: int = 500,
    keep_last_n: int = 2,
) -> List[Orphan]:
    """Find orphan mp4 files in final_dir not in referenced set."""
    if not final_dir.exists():
        return []

    files = sorted(final_dir.glob("*.mp4"))

    # Protect the N most recent files regardless
    protected: set = set()
    if keep_last_n > 0 and files:
        by_mtime = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
        protected = {p.name for p in by_mtime[:keep_last_n]}

    cutoff: Optional[datetime] = None
    if older_than_hours is not None:
        cutoff = _utcnow() - timedelta(hours=older_than_hours)

    orphans: List[Orphan] = []
    for p in files:
        if not p.is_file():
            continue
        if p.name in referenced_filenames:
            continue
        if p.name in protected:
            continue

        st = p.stat()
        if st.st_size < (min_size_kb * 1024):
            continue

        mtime = _file_mtime_utc(p)
        if cutoff and mtime > cutoff:
            continue

        orphans.append(Orphan(path=p, size_bytes=st.st_size, mtime_utc=mtime))

    return orphans


def find_dangling_index_entries(index: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Find index entries whose files no longer exist on disk."""
    dangling: List[Tuple[str, str]] = []
    items = index.get("items", index)
    if not isinstance(items, dict):
        return dangling
    for sha_key, meta in items.items():
        if not isinstance(meta, dict):
            continue
        p = meta.get("path", "")
        if not isinstance(p, str) or not p.strip():
            continue
        if not Path(p).exists():
            dangling.append((sha_key, Path(p).name))
    return dangling


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def quarantine_or_delete(
    orphans: List[Orphan],
    quarantine_dir: Path,
    do_quarantine: bool,
    do_delete: bool,
    dry_run: bool,
) -> Dict[str, int]:
    """Execute quarantine or delete on orphan files."""
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    moved, deleted, failed = 0, 0, 0

    for o in orphans:
        if dry_run:
            continue

        stamp = _utcnow().strftime("%Y%m%d_%H%M%S")
        dst = quarantine_dir / f"{stamp}__orphan__{o.path.name}"

        try:
            if do_delete:
                o.path.unlink(missing_ok=True)
                deleted += 1
            elif do_quarantine:
                os.replace(str(o.path), str(dst))
                moved += 1
        except Exception:
            failed += 1

    return {"moved": moved, "deleted": deleted, "failed": failed}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RayVault Doctor Cleanup (orphan quarantine)",
    )
    parser.add_argument("--index", default=str(DEFAULT_INDEX_PATH))
    parser.add_argument("--final-dir", default=str(DEFAULT_FINAL_DIR))
    parser.add_argument("--quarantine-dir", default=str(DEFAULT_QUARANTINE_DIR))
    parser.add_argument(
        "--older-than-hours", type=float, default=None,
        help="Only consider orphans with mtime older than N hours",
    )
    parser.add_argument(
        "--min-size-kb", type=int, default=500,
        help="Ignore files smaller than N KB (default 500)",
    )
    parser.add_argument(
        "--keep-last-n", type=int, default=2,
        help="Never touch the N most recent mp4s (default 2)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only, no action")
    parser.add_argument("--quarantine", action="store_true", help="Move orphans to quarantine")
    parser.add_argument("--delete", action="store_true", help="DELETE orphans (dangerous)")

    args = parser.parse_args(argv)

    if args.delete and args.quarantine:
        print("Error: use --delete OR --quarantine, not both")
        return 2

    # Default to dry-run if no action specified
    if not args.delete and not args.quarantine:
        args.dry_run = True

    index_path = Path(args.index)
    final_dir = Path(args.final_dir)
    quarantine_dir = Path(args.quarantine_dir)

    try:
        index = _load_index(index_path)
    except RuntimeError as e:
        print(f"Error: {e}")
        return 2

    referenced = _index_referenced_filenames(index)

    orphans = find_orphans(
        final_dir=final_dir,
        referenced_filenames=referenced,
        older_than_hours=args.older_than_hours,
        min_size_kb=args.min_size_kb,
        keep_last_n=args.keep_last_n,
    )

    dangling = find_dangling_index_entries(index)

    # Report
    total_bytes = sum(o.size_bytes for o in orphans)
    print("RayVault Doctor Cleanup")
    print(f"  final_dir: {final_dir}")
    print(f"  index: {index_path} (entries: {len(index.get('items', index))})")
    print(f"  referenced filenames: {len(referenced)}")
    print(f"  orphans found: {len(orphans)} | total size: {human_size(int(total_bytes))}")
    if args.older_than_hours is not None:
        print(f"  filter: older_than_hours={args.older_than_hours}")
    print(f"  filter: min_size_kb={args.min_size_kb}")
    print(f"  safety: keep_last_n={args.keep_last_n}")

    if dangling:
        print(f"\n  Dangling index entries: {len(dangling)} (index points to missing file)")
        for sha, fname in dangling[:8]:
            print(f"    - {sha} -> {fname}")
        if len(dangling) > 8:
            print("    ...")

    if orphans:
        print("\n  Orphan files:")
        for o in orphans[:10]:
            print(
                f"    - {o.path.name} | {human_size(o.size_bytes)} | "
                f"mtime={o.mtime_utc.strftime('%Y-%m-%d %H:%M')}"
            )
        if len(orphans) > 10:
            print(f"    ... ({len(orphans) - 10} more)")

    if args.dry_run:
        print("\nDRY-RUN: no action taken.")
        print("  To quarantine: use --quarantine")
        print("  To delete (dangerous): use --delete")
        return 0

    result = quarantine_or_delete(
        orphans=orphans,
        quarantine_dir=quarantine_dir,
        do_quarantine=args.quarantine,
        do_delete=args.delete,
        dry_run=args.dry_run,
    )

    # Persist cleanup_history in index meta_info
    if not args.dry_run and (result["moved"] > 0 or result["deleted"] > 0):
        try:
            idx = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
            meta = idx.setdefault("meta_info", {})
            history = meta.get("cleanup_history", [])
            history.append({
                "at": _utcnow().isoformat(),
                "orphans_found": len(orphans),
                "moved": result["moved"],
                "deleted": result["deleted"],
                "failed": result["failed"],
                "dangling": len(dangling),
            })
            meta["cleanup_history"] = history[-10:]
            # Atomic write
            tmp = index_path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(idx, f, ensure_ascii=False, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, index_path)
        except Exception:
            pass  # telemetry is best-effort, never fail the cleanup

    if args.quarantine:
        print(
            f"\nQUARANTINE: moved={result['moved']} "
            f"failed={result['failed']} -> {quarantine_dir}"
        )
    elif args.delete:
        print(
            f"\nDELETE: deleted={result['deleted']} "
            f"failed={result['failed']}"
        )

    return 0 if result["failed"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
