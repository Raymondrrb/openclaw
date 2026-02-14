#!/usr/bin/env python3
"""RayVault Doctor Report — Dzine credits audit + cache forensics + financial advisor.

Scans all job manifests and the video index to produce:
1. Credits needed vs saved per run (SKIP_DZINE economy)
2. Obsolete sha8 entries (in index but not referenced by any active job)
3. Optional bitrate gate (detects low-quality exports)
4. Missing video count per run
5. Financial projection (USD + optional BRL via env)
6. Orphan files in /final not tracked by index (zombie search)
7. Timeline CSV with categories, drift, and cumulative drift

Environment variables (optional):
  DZINE_CREDIT_PRICE_USD  — cost per credit in USD (e.g. 1.50)
  USD_BRL                 — fixed FX rate for BRL projection (e.g. 5.00)

Usage:
    python3 scripts/doctor_report.py
    python3 scripts/doctor_report.py --fail-if-needed-gt 0
    python3 scripts/doctor_report.py --fail-if-low-bitrate --bitrate-min-bps 1000000
    python3 scripts/doctor_report.py --orphans
    python3 scripts/doctor_report.py --orphans --move-orphans-to state/video/quarantine
    python3 scripts/doctor_report.py --timeline --timeline-out timeline.csv
    python3 scripts/doctor_report.py --preflight

Exit codes:
    0: OK
    2: Credits needed exceeds threshold (--fail-if-needed-gt)
    3: Low bitrate video detected (--fail-if-low-bitrate)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_STATE_DIR = Path("state")
DEFAULT_CREDIT_COST = 1
DEFAULT_BITRATE_MIN_BPS = 1_000_000  # 1 Mbps

# Category inference from segment_id naming conventions
_CATEGORY_PREFIXES = {
    "intro": "intro",
    "outro": "outro",
    "transition": "transition",
    "hook": "intro",
}


# ---------------------------------------------------------------------------
# JSON IO
# ---------------------------------------------------------------------------

def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


# ---------------------------------------------------------------------------
# ffprobe helpers
# ---------------------------------------------------------------------------

def ffprobe_bitrate_bps(video_path: Path) -> int:
    """Get video bitrate via ffprobe. Returns 0 on failure."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=bit_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return 0
        s = (r.stdout or "").strip()
        return int(float(s)) if s else 0
    except Exception:
        return 0


def _ffprobe_duration_sec(video_path: Path) -> float:
    """Get video duration via ffprobe. Returns 0.0 on failure."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return 0.0
        return float((r.stdout or "").strip() or "0")
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class SegmentRef:
    run_id: str
    segment_id: str
    sha8: str
    target_duration_sec: float
    expected_video_path: Path
    credit_cost: int
    kind: str = "product"
    order: int = 0


@dataclass
class JobSummary:
    run_id: str
    segments_total: int
    segments_skip: int
    segments_need: int
    credits_needed: int
    credits_saved: int
    missing_videos: int
    low_bitrate: int


@dataclass
class TimelineRow:
    order: int
    segment_id: str
    category: str
    start_sec: float
    end_sec: float
    target_duration_sec: float
    source_file: str
    status: str  # READY / MISSING
    probe_duration_sec: float
    delta_sec: float
    cum_drift_sec: float


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _infer_video_path(
    state_dir: Path, run_id: str, segment_id: str, sha8: str,
) -> Path:
    return state_dir / "video" / "final" / f"V_{run_id}_{segment_id}_{sha8}.mp4"


def _infer_category(segment_id: str, kind: str = "") -> str:
    """Infer category from segment_id or kind field."""
    if kind and kind != "product":
        return kind
    sid_lower = segment_id.lower()
    for prefix, cat in _CATEGORY_PREFIXES.items():
        if sid_lower.startswith(prefix):
            return cat
    return "product"


def extract_segment_refs(
    job_doc: dict, state_dir: Path,
) -> List[SegmentRef]:
    """Extract segment references from a job manifest."""
    run_id = job_doc.get("run_id", "UNKNOWN")
    seq = job_doc.get("segments", job_doc.get("sequence", []))
    out: List[SegmentRef] = []

    for i, s in enumerate(seq):
        segment_id = s.get("segment_id", "seg")
        target = float(s.get("approx_duration_sec", s.get("target_duration_sec", 0)))
        audio_sha = s.get("audio_sha256", s.get("audio_digest", ""))
        sha8 = audio_sha[:8] if audio_sha else "unknown"
        kind = s.get("kind", "")

        bc = s.get("dzine", {}).get("budget_control", {})
        credit_cost = int(bc.get("credit_cost", DEFAULT_CREDIT_COST))

        expected = bc.get("expected_video_path")
        if expected:
            expected_path = Path(expected)
        else:
            expected_path = _infer_video_path(state_dir, run_id, segment_id, sha8)

        out.append(SegmentRef(
            run_id=run_id,
            segment_id=segment_id,
            sha8=sha8,
            target_duration_sec=target,
            expected_video_path=expected_path,
            credit_cost=credit_cost,
            kind=kind,
            order=i,
        ))
    return out


def compute_report(
    state_dir: Path = DEFAULT_STATE_DIR,
    bitrate_min_bps: int = DEFAULT_BITRATE_MIN_BPS,
    enable_bitrate_gate: bool = True,
) -> Tuple[List[JobSummary], Dict[str, Any]]:
    """Compute doctor report from jobs + video index.

    Returns (summaries_per_run, global_details).
    """
    jobs_dir = state_dir / "jobs"
    index_path = state_dir / "video" / "index.json"

    idx = _read_json(index_path, default={"items": {}})
    index_items = idx.get("items", {})

    # Collect all job manifests
    job_paths = sorted(jobs_dir.glob("*.json")) if jobs_dir.exists() else []
    all_refs: List[SegmentRef] = []

    for jp in job_paths:
        doc = _read_json(jp, default={})
        refs = extract_segment_refs(doc, state_dir)
        all_refs.extend(refs)

    referenced_sha8 = {r.sha8 for r in all_refs if r.sha8 != "unknown"}

    # Group by run
    by_run: Dict[str, List[SegmentRef]] = {}
    for r in all_refs:
        by_run.setdefault(r.run_id, []).append(r)

    summaries: List[JobSummary] = []
    total_needed = 0
    total_saved = 0
    total_missing = 0
    total_low_br = 0

    for run_id, refs in by_run.items():
        skip = need = credits_n = credits_s = missing = low_br = 0

        for r in refs:
            exists = r.expected_video_path.exists()
            if exists:
                skip += 1
                credits_s += r.credit_cost
                if enable_bitrate_gate:
                    br = ffprobe_bitrate_bps(r.expected_video_path)
                    if 0 < br < bitrate_min_bps:
                        low_br += 1
            else:
                need += 1
                credits_n += r.credit_cost
                missing += 1

        total_needed += credits_n
        total_saved += credits_s
        total_missing += missing
        total_low_br += low_br

        summaries.append(JobSummary(
            run_id=run_id,
            segments_total=len(refs),
            segments_skip=skip,
            segments_need=need,
            credits_needed=credits_n,
            credits_saved=credits_s,
            missing_videos=missing,
            low_bitrate=low_br,
        ))

    # Obsolete hashes: in index but not referenced by any job
    obsolete = sorted(set(index_items.keys()) - referenced_sha8)

    details: Dict[str, Any] = {
        "jobs_found": len(job_paths),
        "runs_found": len(by_run),
        "total_credits_needed": total_needed,
        "total_credits_saved": total_saved,
        "total_missing_videos": total_missing,
        "total_low_bitrate": total_low_br,
        "obsolete_sha8_count": len(obsolete),
        "obsolete_sha8": obsolete[:50],
        "bitrate_min_bps": bitrate_min_bps,
        "bitrate_gate_enabled": enable_bitrate_gate,
        "all_refs": all_refs,
    }
    return summaries, details


# ---------------------------------------------------------------------------
# Financial advisor
# ---------------------------------------------------------------------------

def compute_financial(
    total_credits_needed: int,
    total_credits_saved: int,
    credit_price_usd: float = 0.0,
    usd_brl: float = 0.0,
) -> Dict[str, Any]:
    """Compute financial projection from credit counts + env pricing."""
    result: Dict[str, Any] = {
        "credit_price_usd": credit_price_usd,
        "usd_brl": usd_brl,
    }
    if credit_price_usd > 0:
        result["projected_cost_usd"] = round(total_credits_needed * credit_price_usd, 2)
        result["saved_usd"] = round(total_credits_saved * credit_price_usd, 2)
        if usd_brl > 0:
            result["projected_cost_brl"] = round(
                total_credits_needed * credit_price_usd * usd_brl, 2
            )
            result["saved_brl"] = round(
                total_credits_saved * credit_price_usd * usd_brl, 2
            )
    return result


def _get_env_float(key: str, default: float = 0.0) -> float:
    """Read float from env, return default on missing/invalid."""
    val = os.environ.get(key, "")
    try:
        return float(val) if val else default
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Timeline CSV
# ---------------------------------------------------------------------------

def build_timeline(
    refs: List[SegmentRef],
    include_probe: bool = False,
) -> List[TimelineRow]:
    """Build timeline rows with cumulative start/end and optional probe drift."""
    rows: List[TimelineRow] = []
    cursor = 0.0
    cum_drift = 0.0

    sorted_refs = sorted(refs, key=lambda r: r.order)

    for r in sorted_refs:
        start = cursor
        end = cursor + r.target_duration_sec
        exists = r.expected_video_path.exists()
        status = "READY" if exists else "MISSING"

        probe_dur = 0.0
        if include_probe and exists:
            probe_dur = _ffprobe_duration_sec(r.expected_video_path)

        delta = probe_dur - r.target_duration_sec if probe_dur > 0 else 0.0
        cum_drift += delta

        rows.append(TimelineRow(
            order=r.order,
            segment_id=r.segment_id,
            category=_infer_category(r.segment_id, r.kind),
            start_sec=round(start, 3),
            end_sec=round(end, 3),
            target_duration_sec=r.target_duration_sec,
            source_file=str(r.expected_video_path),
            status=status,
            probe_duration_sec=round(probe_dur, 3),
            delta_sec=round(delta, 3),
            cum_drift_sec=round(cum_drift, 3),
        ))

        cursor = end

    return rows


def timeline_to_csv(rows: List[TimelineRow]) -> str:
    """Serialize timeline rows to CSV string."""
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Order", "Segment_ID", "Category", "Start_Sec", "End_Sec",
        "Target_Duration", "Source_File", "Status",
        "Probe_Duration", "Delta_Sec", "Cum_Drift_Sec",
    ])
    for r in rows:
        writer.writerow([
            r.order, r.segment_id, r.category,
            r.start_sec, r.end_sec, r.target_duration_sec,
            r.source_file, r.status,
            r.probe_duration_sec, r.delta_sec, r.cum_drift_sec,
        ])
    return buf.getvalue()


def save_timeline_csv(
    csv_str: str,
    run_id: str,
    timeline_dir: Path,
) -> Tuple[Path, Path]:
    """Save timeline CSV with automatic timestamp + _latest symlink.

    Creates:
      timeline_{run_id}_{YYYYMMDD_HHMM}.csv  — timestamped snapshot
      timeline_{run_id}_latest.csv            — symlink to latest

    Returns (timestamped_path, latest_path).
    """
    from datetime import datetime, timezone

    timeline_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    timestamped = timeline_dir / f"timeline_{run_id}_{stamp}.csv"
    latest = timeline_dir / f"timeline_{run_id}_latest.csv"

    timestamped.write_text(csv_str, encoding="utf-8")

    # Update _latest symlink (atomic: write tmp symlink then replace)
    tmp_link = latest.with_suffix(".csv.tmp")
    try:
        tmp_link.unlink(missing_ok=True)
        tmp_link.symlink_to(timestamped.name)
        tmp_link.replace(latest)
    except OSError:
        # Fallback for filesystems without symlink support: copy
        latest.write_text(csv_str, encoding="utf-8")

    return timestamped, latest


# ---------------------------------------------------------------------------
# QC Banner — quick drift summary without opening the CSV
# ---------------------------------------------------------------------------

_QC_WARN_DRIFT_SEC = 0.5
_QC_CRITICAL_DRIFT_SEC = 1.0


def build_qc_banner(rows: List[TimelineRow]) -> str:
    """Build a QC banner summarizing drift health.

    Thresholds:
      > 0.5s drift: WARNING
      > 1.0s drift: CRITICAL
    """
    if not rows:
        return "QC: No timeline rows to evaluate."

    probed = [r for r in rows if r.probe_duration_sec > 0]
    if not probed:
        return "QC: No probed segments (run with --include-probe for drift analysis)."

    max_delta_row = max(probed, key=lambda r: abs(r.delta_sec))
    max_delta_abs = abs(max_delta_row.delta_sec)
    cum_drift_abs = abs(probed[-1].cum_drift_sec) if probed else 0.0
    total_ready = sum(1 for r in rows if r.status == "READY")
    total_missing = sum(1 for r in rows if r.status == "MISSING")

    lines = [
        f"QC Banner: {len(rows)} segments | {total_ready} READY | {total_missing} MISSING",
        f"  Max segment drift: {max_delta_row.delta_sec:+.3f}s ({max_delta_row.segment_id})",
        f"  Cumulative drift:  {probed[-1].cum_drift_sec:+.3f}s",
    ]

    if max_delta_abs > _QC_CRITICAL_DRIFT_SEC or cum_drift_abs > _QC_CRITICAL_DRIFT_SEC:
        lines.append("  Status: CRITICAL — drift exceeds 1.0s, timeline will be off")
    elif max_delta_abs > _QC_WARN_DRIFT_SEC or cum_drift_abs > _QC_WARN_DRIFT_SEC:
        lines.append("  Status: WARNING — drift exceeds 0.5s, review before Resolve")
    else:
        lines.append("  Status: OK — drift within tolerance")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orphan search (delegates to dzine_handoff if available, else inline)
# ---------------------------------------------------------------------------

def find_orphan_videos(state_dir: Path) -> List[Path]:
    """Find .mp4 files in final dir not referenced by video index."""
    final_dir = state_dir / "video" / "final"
    index_path = state_dir / "video" / "index.json"

    idx = _read_json(index_path, default={"items": {}})
    items = idx.get("items", {}) or {}
    indexed_paths = {
        v.get("path") for v in items.values() if isinstance(v, dict)
    }
    orphans: List[Path] = []

    if final_dir.exists():
        for fp in sorted(final_dir.glob("*.mp4")):
            if str(fp) not in indexed_paths:
                orphans.append(fp)

    return orphans


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------

def print_report(
    summaries: List[JobSummary],
    details: Dict[str, Any],
    financial: Optional[Dict[str, Any]] = None,
) -> None:
    """Print human-readable report to stdout."""
    print("\nRayVault Doctor Report — Dzine Budget & Cache Audit\n")
    print(f"Jobs: {details['jobs_found']} | Runs: {details['runs_found']}")
    print(
        f"Credits needed: {details['total_credits_needed']} | "
        f"Credits saved (SKIP): {details['total_credits_saved']}"
    )

    # Financial projection
    if financial and financial.get("credit_price_usd", 0) > 0:
        print(
            f"Projected cost: US$ {financial.get('projected_cost_usd', 0):.2f} | "
            f"Saved: US$ {financial.get('saved_usd', 0):.2f}"
        )
        if financial.get("projected_cost_brl") is not None:
            print(
                f"Projected cost: R$ {financial['projected_cost_brl']:.2f} | "
                f"Saved: R$ {financial['saved_brl']:.2f} "
                f"(FX: {financial['usd_brl']})"
            )

    if details["bitrate_gate_enabled"]:
        print(
            f"Low bitrate videos: {details['total_low_bitrate']} "
            f"(min={details['bitrate_min_bps']} bps)"
        )
    print(f"Missing videos: {details['total_missing_videos']}")
    print(
        f"Obsolete hashes (in index, not referenced): "
        f"{details['obsolete_sha8_count']}\n"
    )

    if summaries:
        header = (
            f"{'RUN':<20} {'SEG':>4} {'SKIP':>4} {'NEED':>4} "
            f"{'CR_NEED':>7} {'CR_SAVE':>7} {'MISS':>4} {'LOWBR':>5}"
        )
        print(header)
        print("-" * len(header))
        for s in sorted(summaries, key=lambda x: x.credits_needed, reverse=True):
            print(
                f"{s.run_id:<20} {s.segments_total:>4} {s.segments_skip:>4} "
                f"{s.segments_need:>4} {s.credits_needed:>7} {s.credits_saved:>7} "
                f"{s.missing_videos:>4} {s.low_bitrate:>5}"
            )

    if details["obsolete_sha8_count"] > 0:
        print("\nObsolete sha8 (sample):")
        for h in details["obsolete_sha8"]:
            print(f"  - {h}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RayVault Doctor Report (Dzine credits, cache audit, financial advisor)",
    )
    parser.add_argument("--state-dir", default="state")
    parser.add_argument("--bitrate-min-bps", type=int, default=DEFAULT_BITRATE_MIN_BPS)
    parser.add_argument("--no-bitrate-gate", action="store_true")
    parser.add_argument(
        "--fail-if-needed-gt", type=int, default=-1,
        help="Exit 2 if total_credits_needed > N",
    )
    parser.add_argument(
        "--fail-if-low-bitrate", action="store_true",
        help="Exit 3 if any low bitrate video detected",
    )

    # Orphans
    parser.add_argument(
        "--orphans", action="store_true",
        help="List orphan videos in /final not tracked by index",
    )
    parser.add_argument(
        "--move-orphans-to", default="",
        help="Move orphans to this directory (quarantine, not delete)",
    )

    # Timeline
    parser.add_argument(
        "--timeline", action="store_true",
        help="Generate timeline CSV with segment start/end and status",
    )
    parser.add_argument("--timeline-out", default="", help="Output CSV path (overrides auto-save)")
    parser.add_argument(
        "--timeline-dir", default="state/timeline",
        help="Directory for auto-saved timeline CSVs (default: state/timeline/)",
    )
    parser.add_argument(
        "--include-probe", action="store_true",
        help="Include ffprobe duration + drift in timeline",
    )

    # QC
    parser.add_argument(
        "--qc", action="store_true",
        help="Print QC banner with drift summary (implies --timeline --include-probe)",
    )

    # Preflight
    parser.add_argument(
        "--preflight", action="store_true",
        help="Print preflight summary (credits + readiness)",
    )

    args = parser.parse_args(argv)
    state_dir = Path(args.state_dir)

    summaries, details = compute_report(
        state_dir=state_dir,
        bitrate_min_bps=args.bitrate_min_bps,
        enable_bitrate_gate=not args.no_bitrate_gate,
    )

    # Financial advisor from env
    credit_price_usd = _get_env_float("DZINE_CREDIT_PRICE_USD")
    usd_brl = _get_env_float("USD_BRL")
    financial = compute_financial(
        details["total_credits_needed"],
        details["total_credits_saved"],
        credit_price_usd,
        usd_brl,
    )

    # --qc implies --timeline --include-probe
    if args.qc:
        args.timeline = True
        args.include_probe = True

    print_report(summaries, details, financial)

    # Orphan search
    if args.orphans:
        orphans = find_orphan_videos(state_dir)
        print(f"\nOrphan videos (in /final, not in index): {len(orphans)}")
        for o in orphans:
            print(f"  - {o}")
        if args.move_orphans_to and orphans:
            quarantine = Path(args.move_orphans_to)
            quarantine.mkdir(parents=True, exist_ok=True)
            for o in orphans:
                dest = quarantine / o.name
                shutil.move(str(o), str(dest))
                print(f"  Moved → {dest}")

    # Timeline CSV
    if args.timeline:
        all_refs = details.get("all_refs", [])
        # Infer run_id from refs (use first found, or "unknown")
        run_ids = {r.run_id for r in all_refs if r.run_id != "UNKNOWN"}
        timeline_run_id = sorted(run_ids)[0] if run_ids else "unknown"

        rows = build_timeline(all_refs, include_probe=args.include_probe)
        csv_str = timeline_to_csv(rows)

        if args.timeline_out:
            # Explicit path overrides auto-save
            Path(args.timeline_out).write_text(csv_str, encoding="utf-8")
            print(f"\nTimeline written to {args.timeline_out}")
        else:
            # Auto-save with timestamp + _latest symlink
            ts_path, latest_path = save_timeline_csv(
                csv_str, timeline_run_id, Path(args.timeline_dir),
            )
            print(f"\nTimeline saved: {ts_path}")
            print(f"Timeline latest: {latest_path}")
            print(f"\n--- Timeline CSV ({len(rows)} segments) ---")
            print(csv_str)

        # QC banner (when probe data available)
        if args.include_probe:
            banner = build_qc_banner(rows)
            print(f"\n{banner}")

    # Preflight summary
    if args.preflight:
        needed = details["total_credits_needed"]
        saved = details["total_credits_saved"]
        missing = details["total_missing_videos"]
        print("\n--- Preflight Summary ---")
        print(f"Credits needed: {needed}")
        print(f"Credits saved (cache): {saved}")
        print(f"Missing videos: {missing}")
        if financial.get("projected_cost_usd") is not None:
            print(f"Projected cost: US$ {financial['projected_cost_usd']:.2f}")
        if missing == 0:
            print("Status: ALL READY — no Dzine credits needed")
        else:
            print(f"Status: {missing} segments need rendering")

    if args.fail_if_needed_gt >= 0 and details["total_credits_needed"] > args.fail_if_needed_gt:
        return 2
    if args.fail_if_low_bitrate and details["total_low_bitrate"] > 0:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
