#!/usr/bin/env python3
"""
Pipeline Step 5: Render and upload to YouTube.

Reads timeline_plan.json and script.json, renders via DaVinci,
then uploads to YouTube using the YouTube Data API.

Usage:
    python3 tools/pipeline_step_5_render_upload.py --run-dir content/pipeline_runs/RUN_ID/
    python3 tools/pipeline_step_5_render_upload.py --run-dir content/pipeline_runs/RUN_ID/ --render-only
    python3 tools/pipeline_step_5_render_upload.py --run-dir content/pipeline_runs/RUN_ID/ --upload-only

Input:  {run_dir}/render_ready.flag
        {run_dir}/script.json
        {run_dir}/timeline_plan.json
Output: {run_dir}/render_output/  (rendered video)
        {run_dir}/youtube_url.txt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def check_render_ready(run_dir: Path) -> bool:
    flag = run_dir / "render_ready.flag"
    return flag.exists()


def render_video(run_dir: Path) -> Path | None:
    """Trigger DaVinci render. Returns output path or None."""
    render_dir = run_dir / "render_output"
    render_dir.mkdir(parents=True, exist_ok=True)

    output_file = render_dir / "final.mp4"
    if output_file.exists():
        print(f"[SKIP] Render already exists at {output_file}")
        return output_file

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from resolve_bridge import get_resolve
        resolve = get_resolve()
        if not resolve:
            print("[WARN] DaVinci Resolve not running. Cannot render automatically.")
            print("[ACTION] Open DaVinci Resolve and render manually, then re-run with --upload-only")
            return None

        pm = resolve.GetProjectManager()
        project = pm.GetCurrentProject()
        if not project:
            print("[WARN] No project open in DaVinci Resolve")
            return None

        # Set render settings
        project.SetRenderSettings({
            "TargetDir": str(render_dir),
            "CustomName": "final",
            "FormatWidth": 1920,
            "FormatHeight": 1080,
            "FrameRate": "30",
        })

        pid = project.AddRenderJob()
        if not pid:
            print("[ERROR] Failed to add render job")
            return None

        print(f"[RENDER] Job {pid} queued in DaVinci Resolve")
        project.StartRendering()
        print("[RENDER] Rendering started... (check DaVinci for progress)")
        return output_file

    except (ImportError, Exception) as e:
        print(f"[WARN] DaVinci render not available: {e}")
        print("[ACTION] Render manually in DaVinci, save to:", render_dir)
        return None


def upload_to_youtube(run_dir: Path, video_path: Path) -> str | None:
    """Upload rendered video to YouTube. Returns video URL or None."""
    script_path = run_dir / "script.json"
    if not script_path.exists():
        print("[ERROR] script.json not found for YouTube metadata")
        return None

    script = json.loads(script_path.read_text(encoding="utf-8"))
    yt = script.get("youtube", {})
    title = script.get("video_title", "Untitled")
    description = yt.get("description", "")
    tags = yt.get("tags", [])
    chapters = yt.get("chapters", [])

    # Prepend chapters to description
    if chapters:
        chapter_lines = [f"{ch['time']} {ch['label']}" for ch in chapters]
        description = "\n".join(chapter_lines) + "\n\n" + description

    print(f"[UPLOAD] Title: {title}")
    print(f"[UPLOAD] Tags: {', '.join(tags[:5])}...")
    print(f"[UPLOAD] Description length: {len(description)} chars")

    # YouTube upload requires OAuth2 credentials
    # For now, produce the upload payload for manual upload or YouTube API
    upload_payload = {
        "video_file": str(video_path),
        "title": title,
        "description": description,
        "tags": tags,
        "category_id": "28",  # Science & Technology
        "privacy_status": "private",  # Start as private, publish manually
    }

    payload_path = run_dir / "youtube_upload_payload.json"
    tmp = payload_path.with_suffix(".tmp")
    payload_bytes = json.dumps(upload_payload, indent=2, ensure_ascii=False).encode("utf-8")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, payload_bytes)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(payload_path))
    print(f"[OK] Upload payload saved → {payload_path}")

    # Check for YouTube API credentials
    yt_env = Path(os.path.expanduser("~/.config/newproject/youtube.env"))
    if not yt_env.exists():
        print("[WARN] YouTube API credentials not configured")
        print("[ACTION] Upload manually using youtube_upload_payload.json")
        return None

    print("[TODO] YouTube Data API upload not yet implemented")
    print("[ACTION] Upload manually, then write URL to youtube_url.txt")
    return None


def main():
    parser = argparse.ArgumentParser(description="Step 5: Render and upload")
    parser.add_argument("--run-dir", required=True, help="Pipeline run directory")
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--upload-only", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    url_path = run_dir / "youtube_url.txt"

    if url_path.exists():
        url = url_path.read_text(encoding="utf-8").strip()
        print(f"[SKIP] Already uploaded: {url}")
        sys.exit(0)

    if not check_render_ready(run_dir):
        print("[ERROR] render_ready.flag not found")
        print("[HINT] Run pipeline_step_4_davinci_build.py first")
        sys.exit(1)

    video_path = None

    if not args.upload_only:
        print("[STEP 5a] Rendering video")
        video_path = render_video(run_dir)
        if not video_path or not video_path.exists():
            if not args.render_only:
                print("[BLOCKED] Cannot upload without rendered video")
            sys.exit(0 if args.render_only else 1)
        print(f"[OK] Rendered: {video_path}")

    if args.render_only:
        sys.exit(0)

    # For upload-only, find the rendered file
    if not video_path:
        render_dir = run_dir / "render_output"
        candidates = list(render_dir.glob("*.mp4")) + list(render_dir.glob("*.mov"))
        if not candidates:
            print(f"[ERROR] No rendered video found in {render_dir}")
            sys.exit(1)
        video_path = candidates[0]

    print("[STEP 5b] Uploading to YouTube")
    url = upload_to_youtube(run_dir, video_path)

    if url:
        url_path.write_text(url, encoding="utf-8")
        print(f"[DONE] Uploaded: {url}")
    else:
        print("[DONE] Upload payload ready for manual upload")


if __name__ == "__main__":
    main()
