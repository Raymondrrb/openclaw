#!/usr/bin/env python3
"""Video Study pipeline — automated knowledge extraction from YouTube videos.

Downloads a video, extracts transcript + keyframes, analyzes via Claude
multimodal, and packages structured knowledge into agents/ directory.

All temp data (video, frames, audio) is cleaned up after completion.
Only knowledge.json + knowledge.md persist.

Usage:
    python3 tools/video_study.py study --url "https://youtube.com/watch?v=ABC123"
    python3 tools/video_study.py study --url "..." --context "DaVinci Resolve"
    python3 tools/video_study.py study --file /path/to/video.mp4
    python3 tools/video_study.py study --url "..." --max-frames 120
    python3 tools/video_study.py list
    python3 tools/video_study.py show --video-id ABC123 [--json]

Exit codes: 0=ok, 1=error, 2=action_required (missing deps)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Ensure repo root is on sys.path
_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.common import load_env_file, now_iso

# Load .env early
load_env_file()

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ACTION_REQUIRED = 2


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

def run_study(
    url: str = "",
    file_path: str = "",
    context: str = "",
    max_frames: int = 80,
    frame_strategy: str = "scene",
    video_id_override: str = "",
) -> int:
    """Run the full video study pipeline.

    Returns exit code: 0=success, 1=error, 2=action required.
    """
    from tools.lib.video_study_schema import StudyConfig
    from tools.lib.video_study_download import (
        create_job_dir, cleanup_job_dir, download_video,
        setup_local_file, extract_youtube_id, check_ytdlp, check_ffmpeg,
    )
    from tools.lib.video_study_extract import extract_all, sample_frames
    from tools.lib.video_study_analyze import analyze_video
    from tools.lib.video_study_knowledge import save_knowledge, save_to_supabase, format_study_summary
    from tools.lib.video_study_schema import KnowledgeOutput

    start_time = time.time()

    # Validate config
    config = StudyConfig(
        url=url, file_path=file_path, context=context,
        max_frames=max_frames, frame_strategy=frame_strategy,
    )
    errors = config.validate()
    if errors:
        for e in errors:
            print(f"  Error: {e}")
        return EXIT_ERROR

    # Check dependencies
    if url and not check_ytdlp():
        print("  yt-dlp not found. Install: pip install yt-dlp")
        return EXIT_ACTION_REQUIRED
    if not check_ffmpeg():
        print("  ffmpeg not found. Install: brew install ffmpeg")
        return EXIT_ACTION_REQUIRED

    # Determine video_id
    vid = video_id_override or extract_youtube_id(url) if url else ""
    job_dir = create_job_dir(vid or "")

    print(f"  Job directory: {job_dir}")

    try:
        # Step 1: Download / setup
        print("\n  Step 1/5: Downloading video...")
        if url:
            dl = download_video(url, job_dir)
        else:
            dl = setup_local_file(file_path, job_dir)

        if not dl.success:
            print(f"  Download failed: {dl.error}")
            _try_log_error(dl.video_id or vid, "study_download", dl.error)
            return EXIT_ERROR

        vid = video_id_override or dl.video_id
        print(f"  Video ID: {vid}")
        print(f"  Title: {dl.title}")
        print(f"  Channel: {dl.channel}")
        if dl.duration_s:
            m, s = divmod(int(dl.duration_s), 60)
            print(f"  Duration: {m}:{s:02d}")

        # Step 2: Extract transcript
        print("\n  Step 2/5: Extracting transcript + frames...")
        extraction = extract_all(
            dl.video_path, job_dir,
            subtitle_path=dl.subtitle_path,
            frame_strategy=frame_strategy,
            max_frames=max_frames,
        )

        if not extraction.success:
            print(f"  Extraction failed: {extraction.error}")
            _try_log_error(vid, "study_extract", extraction.error)
            return EXIT_ERROR

        print(f"  Transcript segments: {len(extraction.transcript)}")
        print(f"  Frames extracted: {len(extraction.frames)}")

        # Step 3: Sample frames for API
        print("\n  Step 3/5: Preparing frames for analysis...")
        api_frames = sample_frames(extraction.frames, count=20)
        print(f"  Frames for API: {len(api_frames)}")

        # Step 4: Analyze via Claude
        print("\n  Step 4/5: Analyzing with Claude...")
        knowledge, meta = analyze_video(
            title=dl.title,
            channel=dl.channel,
            description=dl.description,
            transcript_text=extraction.transcript_text,
            frames=api_frames,
            context=context,
        )

        if knowledge is None:
            error_msg = meta.get("error", "Unknown analysis error")
            print(f"  Analysis failed: {error_msg}")
            _try_log_error(vid, "study_analyze", error_msg)
            return EXIT_ERROR

        print(f"  Model: {meta.get('model', '?')}")
        print(f"  Tokens: {meta.get('input_tokens', 0)} in / {meta.get('output_tokens', 0)} out")
        print(f"  Duration: {meta.get('duration_s', 0):.1f}s")

        # Step 5: Package knowledge
        print("\n  Step 5/5: Packaging knowledge...")
        knowledge.video_id = vid
        knowledge.url = url or file_path
        knowledge.study_date = now_iso()[:10]
        knowledge.analysis_meta = meta

        try:
            json_path, md_path = save_knowledge(knowledge)
            print(f"  Saved: {json_path}")
            print(f"  Saved: {md_path}")
        except ValueError as e:
            print(f"  Validation error: {e}")
            _try_log_error(vid, "study_package", str(e))
            return EXIT_ERROR

        # Supabase (fire-and-forget)
        if save_to_supabase(knowledge):
            print("  Supabase: synced")

        # Notify
        _try_notify(vid, knowledge)

        # Summary
        elapsed = time.time() - start_time
        print(f"\n  Study complete in {elapsed:.1f}s")
        print()
        print(format_study_summary(knowledge))

        return EXIT_OK

    finally:
        # GUARANTEED CLEANUP
        print(f"\n  Cleaning up {job_dir}...")
        cleanup_job_dir(job_dir)
        if job_dir.exists():
            print("  WARNING: Job directory still exists after cleanup")
        else:
            print("  Cleanup verified: temp files removed")


# ---------------------------------------------------------------------------
# List / show commands
# ---------------------------------------------------------------------------

def cmd_list() -> int:
    """List all existing video studies."""
    from tools.lib.video_study_knowledge import list_studies, format_studies_list
    studies = list_studies()
    print(format_studies_list(studies))
    return EXIT_OK


def cmd_show(video_id: str, as_json: bool = False) -> int:
    """Show details of a specific study."""
    from tools.lib.video_study_knowledge import load_study, format_study_summary
    knowledge = load_study(video_id)
    if not knowledge:
        print(f"Study not found: {video_id}")
        return EXIT_ERROR

    if as_json:
        print(knowledge.to_json())
    else:
        print(format_study_summary(knowledge))

    return EXIT_OK


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _try_log_error(video_id: str, stage: str, error: str) -> None:
    """Log error to error_log.json. Never raises."""
    try:
        from tools.lib.error_log import log_error
        log_error(video_id, stage, error)
    except Exception:
        pass


def _try_notify(video_id: str, knowledge) -> None:
    """Send Telegram notification. Never raises."""
    try:
        from tools.lib.control_plane import send_telegram
        msg = (
            f"[Rayviews Lab] Video study complete: {video_id}\n"
            f"Title: {knowledge.title}\n"
            f"Insights: {len(knowledge.key_insights)}, "
            f"Actions: {len(knowledge.action_items)}"
        )
        send_telegram(msg)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Video Study — automated knowledge extraction from videos",
    )
    sub = parser.add_subparsers(dest="command", help="Command to run")

    # study
    p_study = sub.add_parser("study", help="Study a video (download, analyze, package)")
    p_study.add_argument("--url", default="", help="YouTube video URL")
    p_study.add_argument("--file", default="", dest="file_path", help="Local video file path")
    p_study.add_argument("--context", default="", help="Context hint (e.g. 'DaVinci Resolve editing')")
    p_study.add_argument("--max-frames", type=int, default=80, help="Max frames to extract (default: 80)")
    p_study.add_argument("--frame-strategy", default="scene", choices=("scene", "interval"),
                         help="Frame extraction strategy (default: scene)")
    p_study.add_argument("--video-id", default="", help="Override video ID")

    # list
    sub.add_parser("list", help="List all existing studies")

    # show
    p_show = sub.add_parser("show", help="Show study details")
    p_show.add_argument("--video-id", required=True, help="Video ID to show")
    p_show.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return EXIT_ERROR

    if args.command == "study":
        print("\n" + "=" * 50)
        print("  Video Study Pipeline")
        print("=" * 50)
        return run_study(
            url=args.url,
            file_path=args.file_path,
            context=args.context,
            max_frames=args.max_frames,
            frame_strategy=args.frame_strategy,
            video_id_override=args.video_id,
        )
    elif args.command == "list":
        return cmd_list()
    elif args.command == "show":
        return cmd_show(args.video_id, as_json=args.json)
    else:
        parser.print_help()
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
