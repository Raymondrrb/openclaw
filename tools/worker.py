#!/usr/bin/env python3
"""RayviewsLab Worker — queue consumer with heartbeat and crash recovery.

Connects all infrastructure:
- RunManager.claim_next() for atomic queue consumption
- HeartbeatManager for lease renewal + panic detection
- Checkpoints for crash recovery (skip completed stages)
- safe_stop for controlled panic shutdown
- Pipeline stages for actual work

Usage:
    # Run continuously (poll every 30s + jitter)
    python3 tools/worker.py --worker-id RayMac-01

    # Single run (process one job and exit)
    python3 tools/worker.py --worker-id RayMac-01 --once

    # Custom settings
    python3 tools/worker.py --worker-id RayMac-01 --lease 15 --poll 60

    # Replay spooled events from previous panic
    python3 tools/worker.py --replay-spool

Stages:
    research → script_brief → script_generate → script_review →
    assets → tts → manifest

Each stage checks the heartbeat, skips if already completed (checkpoint),
and saves progress after completion.
"""

from __future__ import annotations

import argparse
import os
import random
import signal
import sys
import threading
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
_tools = Path(__file__).resolve().parent
if str(_tools) not in sys.path:
    sys.path.insert(0, str(_tools))

from tools.lib.common import load_env_file, now_iso
from tools.lib.run_manager import (
    RunManager,
    HeartbeatManager,
    LostLock,
)
from tools.lib.worker_ops import (
    save_checkpoint,
    load_checkpoint,
    clear_checkpoint,
    safe_stop,
    reset_panic_flag,
    replay_spool,
    mark_worker_panic,
    spool_event,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_POLL_INTERVAL = 30   # seconds between queue polls
DEFAULT_POLL_JITTER = 15     # max random jitter added to poll interval
DEFAULT_LEASE_MINUTES = 15
QUARANTINE_SECONDS = 45      # wait after panic_heartbeat_uncertain before retry

# PID file for safe stop
_RUNTIME_DIR = _repo / "state" / "runtime"
_PID_FILE = _RUNTIME_DIR / "worker.pid"

# Global stop signal — set by SIGINT/SIGTERM or panic
_stop_signal = threading.Event()


# ---------------------------------------------------------------------------
# PID file management
# ---------------------------------------------------------------------------

def write_pid() -> None:
    """Write current PID to state/runtime/worker.pid."""
    _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def remove_pid() -> None:
    """Remove PID file on clean exit."""
    try:
        _PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def read_pid() -> int | None:
    """Read worker PID from file. Returns None if not found."""
    if not _PID_FILE.exists():
        return None
    try:
        return int(_PID_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None

# Pipeline stages in execution order
STAGES = (
    "research",
    "script_brief",
    "script_generate",
    "script_review",
    "assets",
    "tts",
    "manifest",
)


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------

def _handle_signal(signum, frame):
    """Graceful shutdown on SIGINT/SIGTERM."""
    sig_name = signal.Signals(signum).name
    print(f"\n[worker] Received {sig_name} — shutting down gracefully...", file=sys.stderr)
    _stop_signal.set()


# ---------------------------------------------------------------------------
# Stage runners — each returns True on success, False on skip/error
# ---------------------------------------------------------------------------

def _get_video_id(run_id: str, use_supabase: bool) -> str:
    """Get video_id from the pipeline_runs row."""
    if use_supabase:
        try:
            from tools.lib.supabase_client import query
            rows = query("pipeline_runs", filters={"id": run_id}, limit=1)
            if rows:
                return rows[0].get("video_id", "")
        except Exception:
            pass
    return ""


def run_stage_research(video_id: str, run_id: str) -> bool:
    """Evidence-first research: niche → sources → amazon verify → top5."""
    from tools.lib.video_paths import VideoPaths
    paths = VideoPaths(video_id)
    paths.ensure_dirs()

    # Read niche from inputs
    niche = ""
    if paths.niche_txt.exists():
        niche = paths.niche_txt.read_text().strip()

    if not niche:
        print(f"[worker] No niche found for {video_id}", file=sys.stderr)
        return False

    try:
        from tools.research_agent import run_research
        result = run_research(video_id, niche=niche, run_id=run_id)
        return result is not None
    except ImportError:
        print("[worker] research_agent not available — skipping", file=sys.stderr)
        return True  # non-fatal: allow pipeline to continue
    except Exception as exc:
        print(f"[worker] Research failed: {exc}", file=sys.stderr)
        raise


def run_stage_script_brief(video_id: str, run_id: str) -> bool:
    """Generate structured brief from products.json."""
    from tools.lib.video_paths import VideoPaths
    paths = VideoPaths(video_id)

    if not paths.products_json.exists():
        print(f"[worker] No products.json for {video_id}", file=sys.stderr)
        return False

    try:
        from tools.lib.script_brief import generate_brief
        generate_brief(video_id)
        return True
    except ImportError:
        print("[worker] script_brief not available — skipping", file=sys.stderr)
        return True
    except Exception as exc:
        print(f"[worker] Script brief failed: {exc}", file=sys.stderr)
        raise


def run_stage_script_generate(video_id: str, run_id: str) -> bool:
    """Generate script via LLM (OpenAI draft + Anthropic refinement)."""
    from tools.lib.video_paths import VideoPaths
    paths = VideoPaths(video_id)

    try:
        from tools.lib.script_generate import generate_script
        generate_script(video_id)
        return True
    except ImportError:
        print("[worker] script_generate not available — skipping", file=sys.stderr)
        return True
    except Exception as exc:
        print(f"[worker] Script generation failed: {exc}", file=sys.stderr)
        raise


def run_stage_script_review(video_id: str, run_id: str) -> bool:
    """Validate script: hype words, disclosure, compliance."""
    from tools.lib.video_paths import VideoPaths
    paths = VideoPaths(video_id)

    if not paths.script_txt.exists() and not paths.script_final.exists():
        print(f"[worker] No script found for {video_id}", file=sys.stderr)
        return False

    try:
        from tools.lib.script_review import review_script
        result = review_script(video_id)
        return result.get("passed", False) if isinstance(result, dict) else bool(result)
    except ImportError:
        print("[worker] script_review not available — skipping", file=sys.stderr)
        return True
    except Exception as exc:
        print(f"[worker] Script review failed: {exc}", file=sys.stderr)
        raise


def run_stage_assets(video_id: str, run_id: str) -> bool:
    """Generate Dzine assets (thumbnail + product images)."""
    try:
        from tools.lib.dzine_generate import generate_assets
        generate_assets(video_id, run_id=run_id)
        return True
    except ImportError:
        print("[worker] dzine_generate not available — skipping", file=sys.stderr)
        return True
    except Exception as exc:
        print(f"[worker] Asset generation failed: {exc}", file=sys.stderr)
        raise


def run_stage_tts(video_id: str, run_id: str) -> bool:
    """Generate TTS voiceover chunks."""
    try:
        from tools.lib.tts_generate import generate_tts
        generate_tts(video_id)
        return True
    except ImportError:
        print("[worker] tts_generate not available — skipping", file=sys.stderr)
        return True
    except Exception as exc:
        print(f"[worker] TTS generation failed: {exc}", file=sys.stderr)
        raise


def run_stage_manifest(video_id: str, run_id: str) -> bool:
    """Generate DaVinci Resolve edit manifest."""
    try:
        from tools.lib.manifest_generate import generate_manifest
        generate_manifest(video_id)
        return True
    except ImportError:
        print("[worker] manifest_generate not available — skipping", file=sys.stderr)
        return True
    except Exception as exc:
        print(f"[worker] Manifest generation failed: {exc}", file=sys.stderr)
        raise


# Stage name → runner function
STAGE_RUNNERS = {
    "research": run_stage_research,
    "script_brief": run_stage_script_brief,
    "script_generate": run_stage_script_generate,
    "script_review": run_stage_script_review,
    "assets": run_stage_assets,
    "tts": run_stage_tts,
    "manifest": run_stage_manifest,
}


# ---------------------------------------------------------------------------
# Main processing loop for a single run
# ---------------------------------------------------------------------------

def process_run(
    rm: RunManager,
    hb: HeartbeatManager,
    video_id: str,
) -> None:
    """Process a single run through all stages with checkpoint recovery.

    Raises LostLock if the heartbeat detects lock loss.
    Raises Exception on stage failure (rm.fail() is NOT called here).
    """
    run_id = rm.run_id
    ckpt = load_checkpoint(run_id)

    print(f"[worker] Processing run={run_id[:12]}... video={video_id}")
    if ckpt["completed_steps"]:
        print(f"[worker] Resuming from checkpoint: completed={ckpt['completed_steps']}")

    for stage in STAGES:
        # Check for graceful shutdown
        if _stop_signal.is_set():
            print(f"[worker] Stop signal received — pausing at {stage}")
            save_checkpoint(run_id, stage, lock_token=rm.lock_token)
            return

        # Skip completed stages (idempotency)
        if stage in ckpt["completed_steps"]:
            print(f"[worker]   [{stage}] skipped (checkpoint)")
            continue

        # Check heartbeat before expensive work
        hb.check_or_raise()

        print(f"[worker]   [{stage}] starting...")
        t0 = time.monotonic()

        runner = STAGE_RUNNERS[stage]
        ok = runner(video_id, run_id)

        elapsed = time.monotonic() - t0
        if ok:
            print(f"[worker]   [{stage}] done ({elapsed:.1f}s)")
            save_checkpoint(
                run_id, stage,
                lock_token=rm.lock_token,
                data={"elapsed_s": round(elapsed, 1)},
            )
        else:
            print(f"[worker]   [{stage}] returned False — stopping pipeline")
            raise RuntimeError(f"Stage {stage} failed for video {video_id}")

        # Log stage completion as run_event
        rm._log_event("stage_complete", {
            "stage": stage,
            "video_id": video_id,
            "elapsed_s": round(elapsed, 1),
        })

    # All stages complete
    print(f"[worker] All stages complete for run={run_id[:12]}")


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

def worker_loop(
    worker_id: str,
    *,
    lease_minutes: int = DEFAULT_LEASE_MINUTES,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    poll_jitter: int = DEFAULT_POLL_JITTER,
    once: bool = False,
) -> int:
    """Main worker loop: poll → claim → process → repeat.

    Args:
        worker_id: Identifier for this worker (min 3 chars).
        lease_minutes: Lease duration for claimed runs.
        poll_interval: Seconds between polls when queue is empty.
        poll_jitter: Max random jitter on poll interval.
        once: If True, process one run and exit.

    Returns exit code (0=clean, 1=error, 2=interrupted).
    """
    print(f"[worker] Starting worker_id={worker_id} lease={lease_minutes}min "
          f"poll={poll_interval}s once={once}")
    print(f"[worker] Stages: {' → '.join(STAGES)}")

    while not _stop_signal.is_set():
        # --- 1. Try to claim next run ---
        rm = RunManager.claim_next(
            worker_id=worker_id,
            lease_minutes=lease_minutes,
        )

        if rm is None:
            if once:
                print("[worker] No runs available — exiting (--once mode)")
                return 0
            # Sleep with jitter
            sleep_time = poll_interval + random.randint(0, poll_jitter)
            print(f"[worker] Queue empty — sleeping {sleep_time}s")
            if _stop_signal.wait(timeout=sleep_time):
                break  # interrupted
            continue

        # --- 2. Get video_id ---
        video_id = _get_video_id(rm.run_id, rm._use_supabase)
        if not video_id:
            print(f"[worker] No video_id for run {rm.run_id} — skipping")
            rm.fail("no video_id found")
            continue

        # --- 3. Start heartbeat ---
        def on_panic(run_id, reason):
            safe_stop(
                run_id, reason,
                stop_signal=_stop_signal,
                mark_panic_fn=mark_worker_panic,
            )

        hb = rm.start_heartbeat(
            interval_seconds=120,
            jitter_seconds=15,
            on_panic=on_panic,
        )

        # --- 4. Process the run ---
        try:
            process_run(rm, hb, video_id)
            rm.complete()
            clear_checkpoint(rm.run_id)
            print(f"[worker] Run {rm.run_id[:12]} completed successfully")

        except LostLock as exc:
            print(f"[worker] PANIC: {exc}", file=sys.stderr)
            save_checkpoint(rm.run_id, "panic",
                            lock_token=rm.lock_token,
                            data={"panic_reason": str(exc)})
            # Quarantine: wait before retrying (prevents crash loop)
            if hb.panic_type == "panic_heartbeat_uncertain":
                print(f"[worker] Quarantine: waiting {QUARANTINE_SECONDS}s "
                      f"before retry (network uncertain)")
                _stop_signal.wait(timeout=QUARANTINE_SECONDS)
            reset_panic_flag()

        except Exception as exc:
            print(f"[worker] Error: {exc}", file=sys.stderr)
            try:
                rm.fail(str(exc)[:500])
            except Exception:
                pass
            save_checkpoint(rm.run_id, "error",
                            lock_token=rm.lock_token,
                            data={"error": str(exc)[:500]})

        finally:
            rm.stop_heartbeat()

        if once:
            return 0

    print("[worker] Shutdown complete")
    return 0


# ---------------------------------------------------------------------------
# Spool replay
# ---------------------------------------------------------------------------

def cmd_replay_spool() -> int:
    """Replay spooled events to Supabase."""
    print("[worker] Replaying spooled events...")
    result = replay_spool()
    print(f"[worker] Replay done: sent={result['sent']} "
          f"failed={result['failed']} remaining={len(result['remaining'])}")
    return 0 if result["failed"] == 0 else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="RayviewsLab Worker — queue consumer with heartbeat and crash recovery.",
    )
    parser.add_argument(
        "--worker-id", default="",
        help="Worker identifier (min 3 chars). Default: hostname.",
    )
    parser.add_argument(
        "--lease", type=int, default=DEFAULT_LEASE_MINUTES,
        help=f"Lease duration in minutes (default: {DEFAULT_LEASE_MINUTES})",
    )
    parser.add_argument(
        "--poll", type=int, default=DEFAULT_POLL_INTERVAL,
        help=f"Poll interval in seconds (default: {DEFAULT_POLL_INTERVAL})",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Process one run and exit (don't loop)",
    )
    parser.add_argument(
        "--replay-spool", action="store_true",
        help="Replay spooled panic events to Supabase and exit",
    )
    args = parser.parse_args()

    # Load env
    load_env_file()

    # Spool replay mode
    if args.replay_spool:
        return cmd_replay_spool()

    # Worker ID: from arg, env, or hostname
    worker_id = args.worker_id or os.environ.get("WORKER_ID", "")
    if not worker_id:
        import socket
        worker_id = socket.gethostname()

    if len(worker_id.strip()) < 3:
        print("[worker] Error: worker-id must be at least 3 characters", file=sys.stderr)
        return 2

    # Install signal handlers
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # PID file for safe stop
    write_pid()
    try:
        return worker_loop(
            worker_id,
            lease_minutes=args.lease,
            poll_interval=args.poll,
            once=args.once,
        )
    finally:
        remove_pid()


if __name__ == "__main__":
    raise SystemExit(main())
