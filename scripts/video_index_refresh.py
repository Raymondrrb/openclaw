#!/usr/bin/env python3
"""Video Index Refresh — re-probe and enrich state/video/index.json.

Scans all .mp4 files in state/video/final/, validates each with ffprobe,
and upserts enriched metadata into the video index. Incremental by default:
only re-probes files whose (mtime_ns, file_size) pair changed since last refresh.

Features:
  - File lock: advisory flock prevents concurrent read-modify-write races
  - Incremental refresh via (mtime_ns, file_size) dual key (deterministic)
  - Stability gate: skips files still being written (size changing)
  - --force: re-probe everything regardless of cache
  - --allow-missing-sha8: index legacy files without sha8 in filename
  - SHA8 validation: checks filename contains the indexed sha8
  - Root guardrail: rejects files outside state root via relative_to()
  - Dedup: resolved-path dedup prevents double-indexing
  - Enriches: duration, bitrate, video_codec, audio_codec, file_bytes
  - Defensive update: probe fields only overwrite if value is not None
  - Per-item try/except: one bad file never aborts the entire refresh
  - Correct refreshed_at: UTC ISO timestamp (not file mtime)
  - refresh_history: ring buffer of last 10 refreshes in meta_info
  - state_root persisted in meta_info (layout-agnostic)

Usage:
    python3 scripts/video_index_refresh.py
    python3 scripts/video_index_refresh.py --force
    python3 scripts/video_index_refresh.py --allow-missing-sha8
    python3 scripts/video_index_refresh.py --state-dir state --dry-run

Exit codes:
    0: OK
    1: Errors encountered during refresh
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_STATE_DIR = Path("state")
DEFAULT_FINAL_DIR = DEFAULT_STATE_DIR / "video" / "final"
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
# File lock — advisory flock for read-modify-write cycle
# ---------------------------------------------------------------------------

@contextmanager
def _index_lock(index_path: Path, timeout: float = 10.0):
    """Advisory file lock to prevent concurrent index corruption.

    Uses fcntl.flock (Unix). Falls back to no-op on platforms without fcntl.
    """
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
# ffprobe helpers
# ---------------------------------------------------------------------------

def _ffprobe_json(path: Path) -> Optional[dict]:
    """Full ffprobe JSON output."""
    import subprocess
    cmd = [
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return None
        return json.loads(r.stdout or "{}")
    except Exception:
        return None


def _extract_probe_data(meta: dict) -> Dict[str, Any]:
    """Extract duration, bitrate, codecs from ffprobe JSON."""
    fmt = meta.get("format", {})
    dur = 0.0
    try:
        dur = float(fmt.get("duration", 0.0) or 0.0)
    except (ValueError, TypeError):
        pass

    br = 0
    try:
        br_raw = fmt.get("bit_rate")
        br = int(float(br_raw)) if br_raw else 0
    except (ValueError, TypeError):
        pass

    vcodec = None
    acodec = None
    for s in meta.get("streams", []) or []:
        if s.get("codec_type") == "video" and not vcodec:
            vcodec = s.get("codec_name")
        if s.get("codec_type") == "audio" and not acodec:
            acodec = s.get("codec_name")

    return {
        "duration": round(dur, 3),
        "bitrate_bps": br,
        "video_codec": vcodec,
        "audio_codec": acodec,
    }


# ---------------------------------------------------------------------------
# SHA8 helpers
# ---------------------------------------------------------------------------

def _infer_sha8_from_filename(p: Path) -> Optional[str]:
    """Extract sha8 from V_{run_id}_{segment_id}_{sha8}.mp4 naming."""
    m = re.search(r"_([0-9a-fA-F]{8})\.mp4$", p.name)
    return m.group(1).lower() if m else None


def _infer_run_and_segment(p: Path) -> Tuple[str, str]:
    """Infer run_id and segment_id from V_{run_id}_{segment_id}_{sha8}.mp4."""
    name = p.stem  # without .mp4
    if name.startswith("V_"):
        name = name[2:]
    parts = name.rsplit("_", 1)
    if len(parts) == 2:
        prefix, _sha8 = parts
        # prefix might be "RAY-99_intro" → run_id=RAY-99, segment_id=intro
        sub = prefix.split("_", 1)
        if len(sub) == 2:
            return sub[0], sub[1]
        return prefix, "unknown"
    return "unknown", "unknown"


# ---------------------------------------------------------------------------
# Stability + root helpers
# ---------------------------------------------------------------------------

def _is_under_root(p: Path, root: Path) -> bool:
    """Check if resolved path is under root directory."""
    try:
        p.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _is_file_stable(path: Path, sleep_s: float = 0.3) -> bool:
    """Quick stability check: verify file size hasn't changed.

    Catches phantom files still being written (e.g. mid-download).
    Single poll with short sleep — adds 0.3s only for files that
    actually need probing (cached files are skipped before this).
    """
    try:
        s1 = path.stat().st_size
        if s1 == 0:
            return False
        time.sleep(sleep_s)
        s2 = path.stat().st_size
        return s1 == s2
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Core refresh logic
# ---------------------------------------------------------------------------

@dataclass
class RefreshStats:
    """Statistics from an index refresh run."""
    scanned: int = 0
    checked: int = 0
    probed: int = 0
    skipped_mtime: int = 0
    skipped_dedup: int = 0
    skipped_no_sha8: int = 0
    skipped_outside_root: int = 0
    skipped_unstable: int = 0
    enriched: int = 0
    failed_probe: int = 0
    item_error: int = 0
    sha8_mismatch: int = 0


def refresh_index(
    final_dir: Path = DEFAULT_FINAL_DIR,
    index_path: Path = DEFAULT_INDEX_PATH,
    force: bool = False,
    dry_run: bool = False,
    allow_missing_sha8: bool = False,
) -> RefreshStats:
    """Refresh video index by re-probing files in final_dir.

    Incremental by default: only re-probes files whose (mtime_ns, file_size)
    pair changed since the last recorded values in the index entry.

    Uses advisory file lock to prevent concurrent corruption.
    Per-item try/except ensures one bad file never aborts the refresh.

    Args:
        final_dir: Directory containing final .mp4 files.
        index_path: Path to index.json.
        force: If True, re-probe all files regardless of cache.
        dry_run: If True, don't write the index.
        allow_missing_sha8: If True, index files without sha8 in filename.

    Returns:
        RefreshStats with counts of actions taken.
    """
    stats = RefreshStats()

    if not final_dir.exists():
        return stats

    with _index_lock(index_path):
        idx = _load_index(index_path)
        items = idx.setdefault("items", {})

        # Anchor state root from index_path layout (state/video/index.json -> state/)
        state_root = index_path.parent.parent.resolve()

        # Persist state_root in meta_info (layout-agnostic on future reads)
        meta_info = idx.setdefault("meta_info", {})
        declared_root = meta_info.get("state_root")
        if declared_root:
            state_root = Path(declared_root).resolve()
        else:
            meta_info["state_root"] = str(state_root)

        mp4_files = sorted(final_dir.glob("*.mp4"))
        stats.scanned = len(mp4_files)

        seen_paths: set = set()

        for fp in mp4_files:
            try:
                _process_one_file(
                    fp, items, stats, seen_paths, state_root,
                    force=force, allow_missing_sha8=allow_missing_sha8,
                )
            except Exception:
                stats.item_error += 1

        # Persist when any work was done (not just enriched > 0).
        did_work = stats.probed > 0 or stats.enriched > 0 or force
        did_change = stats.enriched > 0

        if not dry_run and did_work:
            history = meta_info.get("refresh_history", [])
            history.append({
                "at": datetime.now(timezone.utc).isoformat(),
                "scanned": stats.scanned,
                "checked": stats.checked,
                "enriched": stats.enriched,
                "failed_probe": stats.failed_probe,
                "skipped_unchanged": stats.skipped_mtime,
                "skipped_dedup": stats.skipped_dedup,
                "skipped_no_sha8": stats.skipped_no_sha8,
                "skipped_outside_root": stats.skipped_outside_root,
                "skipped_unstable": stats.skipped_unstable,
                "item_error": stats.item_error,
                "sha8_mismatch": stats.sha8_mismatch,
                "did_change": did_change,
                "force": force,
                "allow_missing_sha8": allow_missing_sha8,
            })
            meta_info["refresh_history"] = history[-10:]
            _atomic_write_json(index_path, idx)

    return stats


def _process_one_file(
    fp: Path,
    items: dict,
    stats: RefreshStats,
    seen_paths: set,
    state_root: Path,
    *,
    force: bool,
    allow_missing_sha8: bool,
) -> None:
    """Process a single mp4 file for index refresh.

    Extracted to keep the main loop clean and enable per-item try/except.
    """
    # Guard: skip non-files
    if not fp.is_file():
        return

    # Guard: reject files outside state root
    if not _is_under_root(fp, state_root):
        stats.skipped_outside_root += 1
        return

    # Dedup: skip if we've already processed this resolved path
    resolved = str(fp.resolve())
    if resolved in seen_paths:
        stats.skipped_dedup += 1
        return
    seen_paths.add(resolved)

    sha8 = _infer_sha8_from_filename(fp)

    # Gate: reject files without sha8 unless --allow-missing-sha8
    if not sha8 and not allow_missing_sha8:
        stats.skipped_no_sha8 += 1
        return

    stats.checked += 1

    # SHA8 validation: flag mismatch if indexed under different filename
    if sha8 and sha8 in items:
        existing_path = items[sha8].get("path", "")
        if existing_path and Path(existing_path).name != fp.name:
            stats.sha8_mismatch += 1

    # Determine the index key
    key = sha8 if sha8 else fp.stem

    # Incremental check: (mtime_ns, file_size) dual key
    existing = items.get(key, {})
    st = fp.stat()
    current_mtime_ns = st.st_mtime_ns
    current_size = st.st_size

    if not force:
        if (existing.get("file_mtime_ns") == current_mtime_ns
                and existing.get("file_bytes") == current_size):
            stats.skipped_mtime += 1
            return

    # Stability gate: skip files still being written
    if not _is_file_stable(fp):
        stats.skipped_unstable += 1
        return

    # Probe
    stats.probed += 1
    meta = _ffprobe_json(fp)
    if not meta:
        stats.failed_probe += 1
        return

    probe_data = _extract_probe_data(meta)
    run_id, segment_id = _infer_run_and_segment(fp)

    # Build enriched entry (merge with existing, don't overwrite user fields)
    entry = {**existing}
    entry.pop("file_mtime", None)  # migrate from old float key
    entry.update({
        "path": str(fp),
        "run_id": existing.get("run_id") or run_id,
        "segment_id": existing.get("segment_id") or segment_id,
        "file_bytes": current_size,
        "file_mtime_ns": current_mtime_ns,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    })
    # Defensive update: only overwrite probe fields if value is not None.
    if probe_data["duration"] is not None:
        entry["duration"] = probe_data["duration"]
    if probe_data["bitrate_bps"] is not None:
        entry["bitrate_bps"] = probe_data["bitrate_bps"]
    if probe_data["video_codec"] is not None:
        entry["video_codec"] = probe_data["video_codec"]
    if probe_data["audio_codec"] is not None:
        entry["audio_codec"] = probe_data["audio_codec"]

    items[key] = entry
    stats.enriched += 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RayVault Video Index Refresh (re-probe + enrich index.json)",
    )
    parser.add_argument("--state-dir", default="state")
    parser.add_argument(
        "--force", action="store_true",
        help="Re-probe all files regardless of mtime",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Probe but don't write the index",
    )
    parser.add_argument(
        "--allow-missing-sha8", action="store_true",
        help="Index legacy files without sha8 in filename",
    )
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir)
    final_dir = state_dir / "video" / "final"
    index_path = state_dir / "video" / "index.json"

    print("RayVault Video Index Refresh")
    print(f"  final_dir: {final_dir}")
    print(f"  index: {index_path}")
    print(f"  mode: {'FORCE' if args.force else 'incremental'}"
          f"{' (DRY-RUN)' if args.dry_run else ''}"
          f"{' +allow-missing-sha8' if args.allow_missing_sha8 else ''}")

    stats = refresh_index(
        final_dir=final_dir,
        index_path=index_path,
        force=args.force,
        dry_run=args.dry_run,
        allow_missing_sha8=args.allow_missing_sha8,
    )

    print(f"\n  Scanned: {stats.scanned}")
    print(f"  Checked: {stats.checked}")
    print(f"  Probed: {stats.probed}")
    print(f"  Skipped (unchanged): {stats.skipped_mtime}")
    if stats.skipped_dedup > 0:
        print(f"  Skipped (dedup): {stats.skipped_dedup}")
    if stats.skipped_no_sha8 > 0:
        print(f"  Skipped (no sha8): {stats.skipped_no_sha8}")
    if stats.skipped_outside_root > 0:
        print(f"  Skipped (outside root): {stats.skipped_outside_root}")
    if stats.skipped_unstable > 0:
        print(f"  Skipped (unstable): {stats.skipped_unstable}")
    print(f"  Enriched: {stats.enriched}")
    if stats.item_error > 0:
        print(f"  Item errors: {stats.item_error}")
    if stats.failed_probe > 0:
        print(f"  Failed probe: {stats.failed_probe}")
    if stats.sha8_mismatch > 0:
        print(f"  SHA8 mismatch warnings: {stats.sha8_mismatch}")

    did_change = stats.enriched > 0
    print(f"\n  did_work: True | did_change: {did_change}")

    if args.dry_run:
        print("  DRY-RUN: index not written.")

    return 1 if stats.failed_probe > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
