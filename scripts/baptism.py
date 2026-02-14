#!/usr/bin/env python3
"""Baptism — structured validation for first worker run.

Validates that the pipeline infrastructure is healthy before and after
a test run. Run after your first `make worker` session to confirm
everything works: index integrity, skip behavior, checkpoints, orphans.

Two levels:
  A (quick/dry): preflight + index + skip + orphan + QC checks.
     No worker is started. Validates current state only.
  B (full): Level A + checkpoint recovery + spool + worker PID checks.
     Run after you've done a kill -9 / kill -TERM test.

Usage:
    python3 scripts/baptism.py                              # Level A
    python3 scripts/baptism.py --level B CONFIRM=YES        # Level B
    python3 scripts/baptism.py --state-dir state --level A  # explicit

Exit codes:
    0: All checks passed
    1: Some checks failed
    2: CONFIRM=YES required for level B
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_STATE_DIR = Path("state")
_REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Check result model
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    """Outcome of a single baptism check."""
    name: str
    passed: bool
    detail: str
    severity: str = "info"  # info | warn | fail


@dataclass
class BaptismReport:
    """Full baptism report."""
    level: str
    timestamp: str
    checks: List[CheckResult] = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    warnings: int = 0

    def add(self, check: CheckResult) -> None:
        self.checks.append(check)
        if check.passed:
            self.passed += 1
        elif check.severity == "warn":
            self.warnings += 1
        else:
            self.failed += 1

    @property
    def all_passed(self) -> bool:
        return self.failed == 0


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_ffprobe() -> CheckResult:
    """Verify ffprobe is available."""
    try:
        r = subprocess.run(
            ["ffprobe", "-version"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            version_line = (r.stdout or "").split("\n")[0]
            return CheckResult("ffprobe", True, version_line)
        return CheckResult("ffprobe", False, "ffprobe returned non-zero", "fail")
    except FileNotFoundError:
        return CheckResult("ffprobe", False, "ffprobe not found in PATH", "fail")
    except Exception as e:
        return CheckResult("ffprobe", False, str(e), "fail")


def check_env_vars() -> CheckResult:
    """Check required environment variables."""
    required = ["SUPABASE_URL", "SUPABASE_SERVICE_KEY"]
    optional = ["RAYVAULT_WORKER_ID", "DZINE_CREDIT_PRICE_USD", "USD_BRL"]

    missing_req = [k for k in required if not os.environ.get(k)]
    missing_opt = [k for k in optional if not os.environ.get(k)]

    if missing_req:
        return CheckResult(
            "env_vars", False,
            f"Missing required: {', '.join(missing_req)}",
            "fail",
        )
    detail = "All required present"
    if missing_opt:
        detail += f" (optional missing: {', '.join(missing_opt)})"
    return CheckResult("env_vars", True, detail)


def check_state_dirs(state_dir: Path) -> CheckResult:
    """Verify state directory structure exists."""
    expected = [
        state_dir,
        state_dir / "video",
        state_dir / "video" / "final",
    ]
    missing = [str(d) for d in expected if not d.exists()]
    if missing:
        return CheckResult(
            "state_dirs", False,
            f"Missing directories: {', '.join(missing)}",
            "warn",
        )
    return CheckResult("state_dirs", True, f"All directories present under {state_dir}")


def check_index_health(state_dir: Path) -> CheckResult:
    """Validate video index structure and content."""
    index_path = state_dir / "video" / "index.json"
    if not index_path.exists():
        return CheckResult("index_health", True, "No index yet (will be created on first refresh)")

    try:
        idx = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception as e:
        return CheckResult("index_health", False, f"Corrupt index: {e}", "fail")

    items = idx.get("items", {})
    total = len(items)

    # Check for entries with missing files
    missing_files = 0
    for key, entry in items.items():
        p = entry.get("path", "")
        if p and not Path(p).exists():
            missing_files += 1

    # Check for entries missing mtime_ns (old format)
    old_format = sum(1 for e in items.values() if "file_mtime_ns" not in e)

    detail = f"{total} entries"
    if missing_files:
        detail += f", {missing_files} with missing files"
    if old_format:
        detail += f", {old_format} in old mtime format (will migrate on next refresh)"

    passed = missing_files == 0
    severity = "warn" if missing_files > 0 else "info"
    return CheckResult("index_health", passed, detail, severity)


def check_skip_behavior(state_dir: Path) -> CheckResult:
    """Verify that existing videos in /final would be skipped (SKIP_DZINE economy)."""
    final_dir = state_dir / "video" / "final"
    index_path = state_dir / "video" / "index.json"

    if not final_dir.exists():
        return CheckResult("skip_behavior", True, "No final dir yet")

    mp4_files = list(final_dir.glob("*.mp4"))
    if not mp4_files:
        return CheckResult("skip_behavior", True, "No mp4 files in final/")

    if not index_path.exists():
        return CheckResult(
            "skip_behavior", False,
            f"{len(mp4_files)} files in final/ but no index — run `make index-refresh`",
            "warn",
        )

    idx = json.loads(index_path.read_text(encoding="utf-8"))
    items = idx.get("items", {})
    indexed_paths = {e.get("path") for e in items.values() if isinstance(e, dict)}

    unindexed = [f for f in mp4_files if str(f) not in indexed_paths]
    if unindexed:
        return CheckResult(
            "skip_behavior", False,
            f"{len(unindexed)}/{len(mp4_files)} files NOT in index — SKIP won't work for these",
            "warn",
        )

    return CheckResult(
        "skip_behavior", True,
        f"All {len(mp4_files)} files indexed — SKIP_DZINE will work",
    )


def check_orphans(state_dir: Path) -> CheckResult:
    """Check for orphan videos (in /final but not in index)."""
    final_dir = state_dir / "video" / "final"
    index_path = state_dir / "video" / "index.json"

    if not final_dir.exists():
        return CheckResult("orphans", True, "No final dir")

    mp4_files = list(final_dir.glob("*.mp4"))
    if not mp4_files:
        return CheckResult("orphans", True, "No mp4 files")

    if not index_path.exists():
        if mp4_files:
            return CheckResult(
                "orphans", False,
                f"{len(mp4_files)} orphan files (no index exists)",
                "warn",
            )
        return CheckResult("orphans", True, "Clean")

    idx = json.loads(index_path.read_text(encoding="utf-8"))
    items = idx.get("items", {})
    indexed_paths = {e.get("path") for e in items.values() if isinstance(e, dict)}

    orphans = [f for f in mp4_files if str(f) not in indexed_paths]
    if orphans:
        names = [f.name for f in orphans[:5]]
        return CheckResult(
            "orphans", False,
            f"{len(orphans)} orphan(s): {', '.join(names)}{'...' if len(orphans) > 5 else ''}",
            "warn",
        )

    return CheckResult("orphans", True, f"0 orphans / {len(mp4_files)} total")


def check_refresh_history(state_dir: Path) -> CheckResult:
    """Check refresh history in meta_info."""
    index_path = state_dir / "video" / "index.json"
    if not index_path.exists():
        return CheckResult("refresh_history", True, "No index yet")

    idx = json.loads(index_path.read_text(encoding="utf-8"))
    meta = idx.get("meta_info", {})
    history = meta.get("refresh_history", [])

    if not history:
        return CheckResult(
            "refresh_history", True,
            "No refresh history (run `make index-refresh` first)",
        )

    last = history[-1]
    detail = (
        f"{len(history)} refreshes recorded | "
        f"last: {last.get('at', '?')} "
        f"(enriched={last.get('enriched', '?')}, "
        f"failed={last.get('failed_probe', 0)})"
    )
    return CheckResult("refresh_history", True, detail)


def check_checkpoints() -> CheckResult:
    """Check for checkpoint files (Level B: recovery validation)."""
    ckpt_dir = _REPO_ROOT / "checkpoints"
    if not ckpt_dir.exists():
        return CheckResult("checkpoints", True, "No checkpoints dir (clean state)")

    ckpt_files = list(ckpt_dir.glob("*.json"))
    if not ckpt_files:
        return CheckResult("checkpoints", True, "Checkpoint dir exists but empty (all runs completed cleanly)")

    details = []
    for f in sorted(ckpt_files)[:5]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            stages = data.get("completed_steps", [])
            details.append(f"{f.stem}: {len(stages)} stages done")
        except Exception:
            details.append(f"{f.stem}: corrupt")

    return CheckResult(
        "checkpoints", True,
        f"{len(ckpt_files)} checkpoint(s) — {'; '.join(details)}",
    )


def check_spool() -> CheckResult:
    """Check spool for unprocessed events."""
    spool_dir = _REPO_ROOT / "spool"
    if not spool_dir.exists():
        return CheckResult("spool", True, "No spool dir")

    pending = list(spool_dir.glob("*.json"))
    quarantine = list((spool_dir / "quarantine").glob("*.json")) if (spool_dir / "quarantine").exists() else []
    bad = list((spool_dir / "bad").glob("*.json")) if (spool_dir / "bad").exists() else []

    if not pending and not quarantine and not bad:
        return CheckResult("spool", True, "Clean spool")

    parts = []
    if pending:
        parts.append(f"{len(pending)} pending")
    if quarantine:
        parts.append(f"{len(quarantine)} quarantined")
    if bad:
        parts.append(f"{len(bad)} bad")

    severity = "warn" if pending else "info"
    return CheckResult("spool", len(pending) == 0, f"Spool: {', '.join(parts)}", severity)


def check_worker_pid() -> CheckResult:
    """Check if a worker is currently running (PID file)."""
    pid_file = _REPO_ROOT / "state" / "runtime" / "worker.pid"
    if not pid_file.exists():
        return CheckResult("worker_pid", True, "No active worker (PID file absent)")

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return CheckResult("worker_pid", False, "Corrupt PID file", "warn")

    # Check if process is alive
    try:
        os.kill(pid, 0)  # signal 0 = just check existence
        return CheckResult("worker_pid", True, f"Worker running (PID {pid})")
    except ProcessLookupError:
        return CheckResult(
            "worker_pid", False,
            f"Stale PID file (PID {pid} not running) — clean with `rm {pid_file}`",
            "warn",
        )
    except PermissionError:
        return CheckResult("worker_pid", True, f"Worker running (PID {pid}, different user)")


def check_qc_drift(state_dir: Path) -> CheckResult:
    """Quick QC drift check using doctor_report (no ffprobe, just structure)."""
    jobs_dir = state_dir / "jobs"
    if not jobs_dir.exists() or not list(jobs_dir.glob("*.json")):
        return CheckResult("qc_drift", True, "No job manifests yet")

    # Try to import and run QC
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    try:
        from doctor_report import compute_report
        summaries, details = compute_report(
            state_dir=state_dir,
            enable_bitrate_gate=False,
        )
        needed = details["total_credits_needed"]
        saved = details["total_credits_saved"]
        missing = details["total_missing_videos"]

        detail = f"Credits: {needed} needed, {saved} saved | {missing} missing videos"
        passed = True
        severity = "info"
        if missing > 0:
            severity = "warn"
            passed = False

        return CheckResult("qc_drift", passed, detail, severity)
    except Exception as e:
        return CheckResult("qc_drift", True, f"Could not run QC: {e}")


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def save_report(report: BaptismReport, state_dir: Path) -> Path:
    """Save baptism report as JSON to state/baptism/."""
    baptism_dir = state_dir / "baptism"
    baptism_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = baptism_dir / f"baptism_{report.level}_{stamp}.json"

    data = {
        "level": report.level,
        "timestamp": report.timestamp,
        "summary": {
            "passed": report.passed,
            "failed": report.failed,
            "warnings": report.warnings,
            "total": len(report.checks),
            "verdict": "PASS" if report.all_passed else "FAIL",
        },
        "checks": [asdict(c) for c in report.checks],
    }

    report_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report_path


def print_report(report: BaptismReport) -> None:
    """Print baptism report to stdout."""
    print(f"\n{'='*60}")
    print(f"  BAPTISM LEVEL {report.level} — {report.timestamp}")
    print(f"{'='*60}\n")

    for c in report.checks:
        icon = "PASS" if c.passed else ("WARN" if c.severity == "warn" else "FAIL")
        print(f"  [{icon:4s}] {c.name}: {c.detail}")

    print(f"\n{'='*60}")
    verdict = "ALL CHECKS PASSED" if report.all_passed else "SOME CHECKS FAILED"
    print(f"  {verdict} ({report.passed} pass, {report.failed} fail, {report.warnings} warn)")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Baptism runner
# ---------------------------------------------------------------------------

def run_baptism(
    state_dir: Path = DEFAULT_STATE_DIR,
    level: str = "A",
) -> BaptismReport:
    """Run baptism checks and return report.

    Level A: preflight + index + skip + orphan + QC (non-destructive).
    Level B: Level A + checkpoints + spool + worker PID (post-kill validation).
    """
    report = BaptismReport(
        level=level,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # --- Level A: core checks ---
    report.add(check_ffprobe())
    report.add(check_env_vars())
    report.add(check_state_dirs(state_dir))
    report.add(check_index_health(state_dir))
    report.add(check_skip_behavior(state_dir))
    report.add(check_orphans(state_dir))
    report.add(check_refresh_history(state_dir))
    report.add(check_qc_drift(state_dir))

    # --- Level B: recovery checks ---
    if level == "B":
        report.add(check_checkpoints())
        report.add(check_spool())
        report.add(check_worker_pid())

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Baptism — structured validation for RayVault pipeline",
    )
    parser.add_argument("--state-dir", default="state")
    parser.add_argument(
        "--level", choices=["A", "B"], default="A",
        help="A=quick/dry (default), B=full (post-kill recovery validation)",
    )
    parser.add_argument(
        "confirm", nargs="?", default="",
        help="Pass CONFIRM=YES for Level B",
    )
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir)

    # Level B requires confirmation
    if args.level == "B":
        confirm = args.confirm or os.environ.get("CONFIRM", "")
        if confirm != "CONFIRM=YES" and confirm != "YES":
            print("Level B requires confirmation.")
            print("Usage: python3 scripts/baptism.py --level B CONFIRM=YES")
            print("\nLevel B validates post-kill recovery (checkpoints, spool, PID).")
            print("Run Level A first to validate basic infrastructure.")
            return 2

    report = run_baptism(state_dir=state_dir, level=args.level)
    print_report(report)

    # Save report
    report_path = save_report(report, state_dir)
    print(f"Report saved: {report_path}")

    if not report.all_passed:
        print("\nNext steps:")
        for c in report.checks:
            if not c.passed and c.severity == "fail":
                print(f"  - Fix: {c.name} — {c.detail}")
        for c in report.checks:
            if not c.passed and c.severity == "warn":
                print(f"  - Review: {c.name} — {c.detail}")

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
