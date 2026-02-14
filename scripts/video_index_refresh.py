#!/usr/bin/env python3
"""Video Index Refresh — re-probe and enrich state/video/index.json.

Scans all .mp4 files in state/video/final/, validates each with ffprobe,
and upserts enriched metadata into the video index. Incremental by default:
only re-probes files whose mtime changed since last refresh.

Features:
  - Incremental refresh via file mtime (skips unchanged files)
  - --force: re-probe everything regardless of mtime
  - SHA8 validation: checks filename contains the indexed sha8
  - Enriches: duration, bitrate, video_codec, audio_codec, file_bytes
  - Correct refreshed_at: UTC ISO timestamp (not file mtime)

Usage:
    python3 scripts/video_index_refresh.py
    python3 scripts/video_index_refresh.py --force
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
# Core refresh logic
# ---------------------------------------------------------------------------

@dataclass
class RefreshStats:
    """Statistics from an index refresh run."""
    scanned: int = 0
    probed: int = 0
    skipped_mtime: int = 0
    enriched: int = 0
    failed_probe: int = 0
    sha8_mismatch: int = 0


def refresh_index(
    final_dir: Path = DEFAULT_FINAL_DIR,
    index_path: Path = DEFAULT_INDEX_PATH,
    force: bool = False,
    dry_run: bool = False,
) -> RefreshStats:
    """Refresh video index by re-probing files in final_dir.

    Incremental by default: only re-probes files whose mtime changed
    since the last recorded file_mtime in the index entry.

    Args:
        final_dir: Directory containing final .mp4 files.
        index_path: Path to index.json.
        force: If True, re-probe all files regardless of mtime.
        dry_run: If True, don't write the index.

    Returns:
        RefreshStats with counts of actions taken.
    """
    idx = _load_index(index_path)
    items = idx.setdefault("items", {})
    stats = RefreshStats()

    if not final_dir.exists():
        return stats

    mp4_files = sorted(final_dir.glob("*.mp4"))
    stats.scanned = len(mp4_files)

    for fp in mp4_files:
        if not fp.is_file():
            continue

        sha8 = _infer_sha8_from_filename(fp)

        # SHA8 validation: if file has sha8 in name and it's already indexed
        # under a different sha8, flag mismatch
        if sha8 and sha8 in items:
            existing_path = items[sha8].get("path", "")
            if existing_path and Path(existing_path).name != fp.name:
                stats.sha8_mismatch += 1

        # Determine the index key
        key = sha8 if sha8 else fp.stem

        # Incremental check: skip if file mtime hasn't changed
        existing = items.get(key, {})
        current_mtime = fp.stat().st_mtime
        if not force and existing.get("file_mtime") == current_mtime:
            stats.skipped_mtime += 1
            continue

        # Probe
        stats.probed += 1
        meta = _ffprobe_json(fp)
        if not meta:
            stats.failed_probe += 1
            continue

        probe_data = _extract_probe_data(meta)
        run_id, segment_id = _infer_run_and_segment(fp)

        # Build enriched entry (merge with existing, don't overwrite user fields)
        entry = {**existing}
        entry.update({
            "path": str(fp),
            "run_id": existing.get("run_id") or run_id,
            "segment_id": existing.get("segment_id") or segment_id,
            "duration": probe_data["duration"],
            "bitrate_bps": probe_data["bitrate_bps"],
            "video_codec": probe_data["video_codec"],
            "audio_codec": probe_data["audio_codec"],
            "file_bytes": fp.stat().st_size,
            "file_mtime": current_mtime,
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
        })

        items[key] = entry
        stats.enriched += 1

    if not dry_run and stats.enriched > 0:
        _atomic_write_json(index_path, idx)

    return stats


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
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir)
    final_dir = state_dir / "video" / "final"
    index_path = state_dir / "video" / "index.json"

    print("RayVault Video Index Refresh")
    print(f"  final_dir: {final_dir}")
    print(f"  index: {index_path}")
    print(f"  mode: {'FORCE' if args.force else 'incremental'}"
          f"{' (DRY-RUN)' if args.dry_run else ''}")

    stats = refresh_index(
        final_dir=final_dir,
        index_path=index_path,
        force=args.force,
        dry_run=args.dry_run,
    )

    print(f"\n  Scanned: {stats.scanned}")
    print(f"  Probed: {stats.probed}")
    print(f"  Skipped (mtime unchanged): {stats.skipped_mtime}")
    print(f"  Enriched: {stats.enriched}")
    if stats.failed_probe > 0:
        print(f"  Failed probe: {stats.failed_probe}")
    if stats.sha8_mismatch > 0:
        print(f"  SHA8 mismatch warnings: {stats.sha8_mismatch}")

    if args.dry_run:
        print("\nDRY-RUN: index not written.")

    return 1 if stats.failed_probe > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
