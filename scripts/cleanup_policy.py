#!/usr/bin/env python3
"""Cleanup Policy — delete stale audio, video, and trace files by age.

Prevents disk bloat from accumulated pipeline runs.  Runs as a cron job
or manually after a batch of runs.

Targets:
  - state/audio/<run_id>/  — per-segment mp3 files
  - state/video/<run_id>/  — per-segment mp4 files
  - state/checkpoints/     — checkpoint JSON files
  - state/jobs/            — manifest JSON files

Safety:
  - Dry-run by default (--dry-run flag; use --execute to actually delete)
  - Never touches state/output/ (final renders are precious)
  - Logs every deletion to stderr for audit

Usage:
    python3 scripts/cleanup_policy.py --audio-days 14 --traces-days 30
    python3 scripts/cleanup_policy.py --audio-days 7 --execute

Exit codes:
    0: Success (or dry-run complete)
    1: Runtime error
    2: Bad arguments
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


def _age_days(path: Path) -> float:
    """Get file/dir age in days from mtime."""
    try:
        mtime = path.stat().st_mtime
        return (time.time() - mtime) / 86400.0
    except OSError:
        return 0.0


def _collect_stale(base: Path, max_age_days: float) -> list[Path]:
    """Collect paths (files or run dirs) older than max_age_days."""
    stale: list[Path] = []
    if not base.exists():
        return stale

    for child in sorted(base.iterdir()):
        if child.name.startswith("."):
            continue
        if _age_days(child) >= max_age_days:
            stale.append(child)
    return stale


def _delete_path(path: Path, dry_run: bool) -> int:
    """Delete a file or directory tree. Returns bytes freed."""
    freed = 0
    if path.is_dir():
        for f in path.rglob("*"):
            if f.is_file():
                freed += f.stat().st_size
        if dry_run:
            print(f"  [dry-run] would delete dir: {path} ({freed} bytes)", file=sys.stderr)
        else:
            import shutil
            shutil.rmtree(path, ignore_errors=True)
            print(f"  deleted dir: {path} ({freed} bytes)", file=sys.stderr)
    elif path.is_file():
        freed = path.stat().st_size
        if dry_run:
            print(f"  [dry-run] would delete: {path} ({freed} bytes)", file=sys.stderr)
        else:
            path.unlink(missing_ok=True)
            print(f"  deleted: {path} ({freed} bytes)", file=sys.stderr)
    return freed


def run_cleanup(
    *,
    state_dir: str = "state",
    audio_days: float = 14.0,
    video_days: float = 14.0,
    traces_days: float = 30.0,
    dry_run: bool = True,
) -> dict:
    """Run cleanup policy. Returns summary dict."""
    base = Path(state_dir)
    summary = {
        "audio_deleted": 0,
        "video_deleted": 0,
        "checkpoints_deleted": 0,
        "jobs_deleted": 0,
        "total_bytes_freed": 0,
        "dry_run": dry_run,
    }

    # Audio run directories
    audio_base = base / "audio"
    for p in _collect_stale(audio_base, audio_days):
        summary["total_bytes_freed"] += _delete_path(p, dry_run)
        summary["audio_deleted"] += 1

    # Video run directories
    video_base = base / "video"
    for p in _collect_stale(video_base, video_days):
        summary["total_bytes_freed"] += _delete_path(p, dry_run)
        summary["video_deleted"] += 1

    # Checkpoint files
    check_base = base / "checkpoints"
    for p in _collect_stale(check_base, traces_days):
        if p.suffix == ".json":
            summary["total_bytes_freed"] += _delete_path(p, dry_run)
            summary["checkpoints_deleted"] += 1

    # Job manifest files
    jobs_base = base / "jobs"
    for p in _collect_stale(jobs_base, traces_days):
        if p.suffix == ".json":
            summary["total_bytes_freed"] += _delete_path(p, dry_run)
            summary["jobs_deleted"] += 1

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Cleanup stale pipeline artifacts by age.",
    )
    parser.add_argument(
        "--state-dir", default="state",
        help="Root state directory (default: state)",
    )
    parser.add_argument(
        "--audio-days", type=float, default=14.0,
        help="Delete audio/video older than N days (default: 14)",
    )
    parser.add_argument(
        "--video-days", type=float, default=14.0,
        help="Delete video older than N days (default: 14)",
    )
    parser.add_argument(
        "--traces-days", type=float, default=30.0,
        help="Delete checkpoints/jobs older than N days (default: 30)",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually delete files (default is dry-run)",
    )

    args = parser.parse_args()
    dry_run = not args.execute

    if dry_run:
        print("=== DRY RUN (use --execute to delete) ===", file=sys.stderr)

    summary = run_cleanup(
        state_dir=args.state_dir,
        audio_days=args.audio_days,
        video_days=args.video_days,
        traces_days=args.traces_days,
        dry_run=dry_run,
    )

    freed_mb = summary["total_bytes_freed"] / (1024 * 1024)
    mode = "dry-run" if dry_run else "executed"
    print(
        f"Cleanup {mode}: "
        f"audio={summary['audio_deleted']} "
        f"video={summary['video_deleted']} "
        f"checkpoints={summary['checkpoints_deleted']} "
        f"jobs={summary['jobs_deleted']} "
        f"freed={freed_mb:.1f}MB"
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
