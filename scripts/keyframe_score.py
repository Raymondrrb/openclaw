#!/usr/bin/env python3
"""RayVault Keyframe Scorer — score keyframes against visual QC rubric.

Reads keyframe metadata from the video index and scores each entry
against the visual_qc.json rubric. Persists scores in index entries.

Modes:
  - Dry-run (default): report scores without modifying index
  - --apply: persist scores into index entries
  - --baptism: run baptism visual protocol (summary stats only)

Scoring sources:
  - Manual: operator fills scores via --score sha8 criterion=value ...
  - Batch: operator reviews and scores offline, imports CSV

The script does NOT do computer vision. It provides the framework
for tracking and enforcing human QC scores systematically.

Usage:
    python3 scripts/keyframe_score.py --state-dir state
    python3 scripts/keyframe_score.py --state-dir state --score aabbccdd identity=2 lipsync_ready=2 face_artifacts=1 hands_body=2 consistency=2
    python3 scripts/keyframe_score.py --state-dir state --baptism
    python3 scripts/keyframe_score.py --state-dir state --summary

Exit codes:
    0: OK
    1: Unscored entries exist
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
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_STATE_DIR = Path("state")
DEFAULT_INDEX_PATH = DEFAULT_STATE_DIR / "video" / "index.json"
RUBRIC_PATH = Path(__file__).resolve().parent.parent / "config" / "visual_qc.json"

CRITERIA = ["identity", "hands_body", "face_artifacts", "consistency", "lipsync_ready"]


# ---------------------------------------------------------------------------
# Atomic JSON I/O (shared pattern)
# ---------------------------------------------------------------------------

def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _load_index(index_path: Path) -> dict:
    if not index_path.exists():
        return {"version": "1.0", "items": {}}
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": "1.0", "items": {}}


def _load_rubric(rubric_path: Path = RUBRIC_PATH) -> dict:
    """Load visual QC rubric config."""
    if not rubric_path.exists():
        return {}
    return json.loads(rubric_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# File lock
# ---------------------------------------------------------------------------

@contextmanager
def _index_lock(index_path: Path, timeout: float = 10.0):
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
# Scoring logic
# ---------------------------------------------------------------------------

def compute_zone(scores: Dict[str, int], rubric: dict) -> str:
    """Determine zone (red/yellow/green) from criterion scores.

    Args:
        scores: {criterion: score} where score is 0-2.
        rubric: loaded visual_qc.json.

    Returns:
        "red", "yellow", or "green".
    """
    total = sum(scores.values())

    # Red zone: any critical criterion at 0
    red_criteria = {"identity", "face_artifacts", "lipsync_ready"}
    for c in red_criteria:
        if scores.get(c, 2) == 0:
            return "red"

    # Green zone: total >= 8, all >= 1, identity and lipsync both 2
    green_reqs = rubric.get("zones", {}).get("green", {}).get("requirements", {})
    min_total = green_reqs.get("min_total", 8)
    min_per = green_reqs.get("min_per_criterion", 1)
    if (total >= min_total
            and all(s >= min_per for s in scores.values())
            and scores.get("identity", 0) >= 2
            and scores.get("lipsync_ready", 0) >= 2):
        return "green"

    # Yellow: passes daily but not library
    if total >= rubric.get("scoring", {}).get("pass_daily", 7):
        return "yellow"

    return "red"


def score_entry(
    sha8: str,
    criterion_scores: Dict[str, int],
    index_path: Path = DEFAULT_INDEX_PATH,
    apply: bool = False,
    rubric_path: Path = RUBRIC_PATH,
) -> Dict[str, Any]:
    """Score a single index entry.

    Args:
        sha8: The entry key.
        criterion_scores: {criterion: score} values 0-2.
        index_path: Path to index.json.
        apply: If True, persist scores in index.
        rubric_path: Path to visual_qc.json.

    Returns:
        Dict with scoring results.
    """
    now = datetime.now(timezone.utc).isoformat()
    rubric = _load_rubric(rubric_path)

    # Validate criterion names
    for c in criterion_scores:
        if c not in CRITERIA:
            return {"error": f"Unknown criterion: {c}", "valid_criteria": CRITERIA}

    # Validate score range
    for c, v in criterion_scores.items():
        if not isinstance(v, int) or v < 0 or v > 2:
            return {"error": f"Score for {c} must be 0, 1, or 2 (got {v})"}

    total = sum(criterion_scores.get(c, 0) for c in CRITERIA)
    zone = compute_zone(criterion_scores, rubric)

    result = {
        "sha8": sha8,
        "scores": criterion_scores,
        "total": total,
        "max": 10,
        "zone": zone,
        "scored_at": now,
        "apply": apply,
    }

    if apply:
        with _index_lock(index_path):
            idx = _load_index(index_path)
            items = idx.get("items", {})
            if sha8 not in items:
                result["error"] = f"Entry {sha8} not found in index"
                return result

            items[sha8]["visual_qc"] = {
                "scores": criterion_scores,
                "total": total,
                "zone": zone,
                "scored_at": now,
            }

            # Persist scoring history
            meta_info = idx.setdefault("meta_info", {})
            history = meta_info.get("score_history", [])
            history.append({
                "sha8": sha8,
                "total": total,
                "zone": zone,
                "at": now,
            })
            meta_info["score_history"] = history[-50:]

            _atomic_write_json(index_path, idx)
            result["persisted"] = True

    return result


def summary(index_path: Path = DEFAULT_INDEX_PATH) -> Dict[str, Any]:
    """Summarize visual QC state across all index entries.

    Returns:
        Dict with counts by zone, unscored count, library-ready count.
    """
    idx = _load_index(index_path)
    items = idx.get("items", {})

    stats = {
        "total_items": 0,
        "scored": 0,
        "unscored": 0,
        "green": 0,
        "yellow": 0,
        "red": 0,
        "library_ready": 0,
        "avg_score": 0.0,
        "lowest_entries": [],
    }

    score_sum = 0
    scored_entries = []

    for sha8, meta in items.items():
        if not isinstance(meta, dict):
            continue
        stats["total_items"] += 1

        qc = meta.get("visual_qc")
        if not qc:
            stats["unscored"] += 1
            continue

        stats["scored"] += 1
        total = qc.get("total", 0)
        zone = qc.get("zone", "red")
        score_sum += total

        if zone == "green":
            stats["green"] += 1
            stats["library_ready"] += 1
        elif zone == "yellow":
            stats["yellow"] += 1
        else:
            stats["red"] += 1

        scored_entries.append((sha8, total, zone))

    if stats["scored"] > 0:
        stats["avg_score"] = round(score_sum / stats["scored"], 1)

    # Lowest 5 entries
    scored_entries.sort(key=lambda x: x[1])
    stats["lowest_entries"] = scored_entries[:5]

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RayVault Keyframe Scorer — score against visual QC rubric",
    )
    parser.add_argument("--state-dir", default="state")
    parser.add_argument(
        "--score", nargs="+", metavar="SHA8_OR_CRITERION",
        help="Score an entry: sha8 identity=2 lipsync_ready=2 ...",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Persist scores in index",
    )
    parser.add_argument(
        "--summary", action="store_true",
        help="Show scoring summary",
    )
    parser.add_argument(
        "--baptism", action="store_true",
        help="Show baptism visual stats (pass rates by block)",
    )
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir)
    index_path = state_dir / "video" / "index.json"

    print("RayVault Keyframe Scorer")
    print(f"  index: {index_path}")

    if args.score:
        # Parse: first arg is sha8, rest are criterion=value
        sha8 = args.score[0]
        scores = {}
        for s in args.score[1:]:
            if "=" not in s:
                print(f"  ERROR: invalid score format '{s}' (expected criterion=value)")
                return 2
            k, v = s.split("=", 1)
            try:
                scores[k] = int(v)
            except ValueError:
                print(f"  ERROR: score value must be integer (got '{v}')")
                return 2

        result = score_entry(
            sha8=sha8,
            criterion_scores=scores,
            index_path=index_path,
            apply=args.apply,
        )

        if "error" in result:
            print(f"  ERROR: {result['error']}")
            return 2

        print(f"\n  Entry: {result['sha8']}")
        print(f"  Total: {result['total']}/{result['max']}")
        print(f"  Zone: {result['zone'].upper()}")
        for c in CRITERIA:
            if c in result["scores"]:
                print(f"    {c}: {result['scores'][c]}/2")
        if args.apply:
            print(f"\n  Score persisted in index.")
        else:
            print(f"\n  DRY-RUN: use --apply to persist.")
        return 0

    if args.summary or args.baptism:
        stats = summary(index_path)
        print(f"\n  Total items: {stats['total_items']}")
        print(f"  Scored: {stats['scored']}")
        print(f"  Unscored: {stats['unscored']}")
        if stats["scored"] > 0:
            print(f"  Avg score: {stats['avg_score']}/10")
            print(f"  Green (library-ready): {stats['green']}")
            print(f"  Yellow (daily-ok): {stats['yellow']}")
            print(f"  Red (reject): {stats['red']}")

            if args.baptism and stats["scored"] >= 10:
                pass_rate = (stats["green"] + stats["yellow"]) / stats["scored"]
                print(f"\n  Baptism pass rate: {pass_rate:.0%}")
                if pass_rate >= 0.8:
                    print("  Verdict: AUTOMATE with QC + re-try")
                elif pass_rate >= 0.5:
                    print("  Verdict: AUTOMATE with fallbacks (keyframe library + regen)")
                else:
                    print("  Verdict: USE FIXED LIBRARY + small variations only")

            if stats["lowest_entries"]:
                print(f"\n  Lowest scored entries:")
                for sha8, total, zone in stats["lowest_entries"]:
                    print(f"    - {sha8}: {total}/10 [{zone}]")

        return 1 if stats["unscored"] > 0 else 0

    # Default: just show summary
    stats = summary(index_path)
    print(f"\n  Items: {stats['total_items']} | Scored: {stats['scored']} | Unscored: {stats['unscored']}")
    if stats["scored"] > 0:
        print(f"  Green: {stats['green']} | Yellow: {stats['yellow']} | Red: {stats['red']}")
    return 1 if stats["unscored"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
