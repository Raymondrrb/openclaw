#!/usr/bin/env python3
"""CLI for checking pipeline status per video_id.

Works even if Telegram is down — reads from local .status.json files.

Usage:
    python3 tools/pipeline_status.py --video-id my-video
    python3 tools/pipeline_status.py --all
    python3 tools/pipeline_status.py --video-id my-video --notify-test
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.common import load_env_file, project_root
from tools.lib.pipeline_status import (
    STAGES,
    VIDEOS_BASE,
    format_status_text,
    get_status,
)


def cmd_status(video_id: str) -> int:
    """Print status for a single video_id."""
    print(format_status_text(video_id))
    return 0


def cmd_all() -> int:
    """Print status summary for all videos with .status.json."""
    if not VIDEOS_BASE.is_dir():
        print("No videos directory found")
        return 0

    found = False
    for d in sorted(VIDEOS_BASE.iterdir()):
        status_file = d / ".status.json"
        if status_file.is_file():
            found = True
            status = get_status(d.name)
            stage = status.stage or "not started"
            milestone = status.milestone or "-"
            errs = len(status.errors)
            done = "DONE" if status.completed_at else "running"

            progress = ""
            if status.progress_total > 0:
                progress = f" ({status.progress_done}/{status.progress_total})"

            err_flag = f" [{errs} errors]" if errs else ""
            print(f"  {d.name:30s} {stage:12s} / {milestone:20s} {done}{progress}{err_flag}")

    if not found:
        print("No video pipelines found. Start with:")
        print("  python3 tools/resolve_manifest.py --scaffold --video-id <name>")

    return 0


def cmd_notify_test(video_id: str) -> int:
    """Send a test notification to Telegram."""
    from tools.lib.notify import notify_progress

    ok = notify_progress(
        video_id,
        stage="test",
        milestone="notification_test",
        next_action="This is a test. No action required.",
        details=["Telegram integration is working"],
    )
    if ok:
        print("Test notification sent to Telegram")
    else:
        print("Failed to send — check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline status viewer")
    parser.add_argument("--video-id", default=None, help="Video project identifier")
    parser.add_argument("--all", action="store_true", help="Show all video pipelines")
    parser.add_argument("--notify-test", action="store_true", help="Send test Telegram notification")
    args = parser.parse_args()

    load_env_file(project_root() / ".env")

    if args.notify_test:
        vid = args.video_id or "test"
        return cmd_notify_test(vid)

    if args.all:
        return cmd_all()

    if args.video_id:
        return cmd_status(args.video_id)

    print("Specify --video-id <id> or --all", file=sys.stderr)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
