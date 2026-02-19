#!/usr/bin/env python3
"""
Pipeline Step 6: Collect video metrics after publishing.

Runs 24h after upload. Reads youtube_url.txt and collects performance data.
Saves to Supabase for learning loop.

Usage:
    python3 tools/pipeline_step_6_collect_metrics.py --run-dir content/pipeline_runs/RUN_ID/

Input:  {run_dir}/youtube_url.txt
Output: {run_dir}/metrics.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


def load_youtube_api_key() -> str:
    env_file = Path(os.path.expanduser("~/.config/newproject/youtube.env"))
    if not env_file.exists():
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("YOUTUBE_API_KEY="):
            return line.split("=", 1)[1].strip()
    return ""


def extract_video_id(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if "youtube.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        return qs.get("v", [""])[0]
    if "youtu.be" in parsed.netloc:
        return parsed.path.lstrip("/")
    return ""


def fetch_video_stats(video_id: str, api_key: str) -> dict:
    url = (
        f"https://www.googleapis.com/youtube/v3/videos"
        f"?part=statistics,contentDetails"
        f"&id={video_id}"
        f"&key={api_key}"
    )
    req = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        # Redact API key from error messages to prevent leaking in tracebacks
        sanitized = str(exc).replace(api_key, "***")
        raise RuntimeError(f"YouTube API call failed: {sanitized}") from None

    items = data.get("items", [])
    if not items:
        return {}

    stats = items[0].get("statistics", {})
    details = items[0].get("contentDetails", {})

    return {
        "video_id": video_id,
        "view_count": int(stats.get("viewCount", 0)),
        "like_count": int(stats.get("likeCount", 0)),
        "comment_count": int(stats.get("commentCount", 0)),
        "duration": details.get("duration", ""),
    }


def sync_to_supabase(metrics: dict, run_slug: str) -> bool:
    """Fire-and-forget write to Supabase."""
    env_file = Path(os.path.expanduser("~/.config/newproject/supabase.env"))
    if not env_file.exists():
        return False

    url = ""
    key = ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("SUPABASE_URL="):
            url = line.split("=", 1)[1].strip()
        elif line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
            key = line.split("=", 1)[1].strip()

    if not url or not key:
        return False

    try:
        import urllib.request
        endpoint = f"{url}/rest/v1/video_metrics"
        payload = json.dumps({
            "run_slug": run_slug,
            **metrics,
        }).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Prefer": "return=minimal",
            },
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Step 6: Collect video metrics")
    parser.add_argument("--run-dir", required=True, help="Pipeline run directory")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    url_path = run_dir / "youtube_url.txt"
    metrics_path = run_dir / "metrics.json"

    if metrics_path.exists():
        print(f"[SKIP] metrics.json already exists at {metrics_path}")
        sys.exit(0)

    if not url_path.exists():
        print("[ERROR] youtube_url.txt not found")
        print("[HINT] Run pipeline_step_5_render_upload.py first")
        sys.exit(1)

    youtube_url = url_path.read_text(encoding="utf-8").strip()
    video_id = extract_video_id(youtube_url)

    if not video_id:
        print(f"[ERROR] Cannot extract video ID from: {youtube_url}")
        sys.exit(1)

    api_key = load_youtube_api_key()
    if not api_key:
        print("[ERROR] YouTube API key not configured")
        sys.exit(1)

    print(f"[STEP 6] Collecting metrics for video {video_id}")

    stats = fetch_video_stats(video_id, api_key)
    if not stats:
        print(f"[ERROR] Could not fetch stats for {video_id}")
        sys.exit(1)

    # Load script data for context
    script_path = run_dir / "script.json"
    script_context = {}
    if script_path.exists():
        script = json.loads(script_path.read_text(encoding="utf-8"))
        script_context = {
            "video_title": script.get("video_title", ""),
            "total_segments": len(script.get("segments", [])),
            "total_word_count": script.get("total_word_count", 0),
        }

    # Derive run_slug from directory name
    run_slug = run_dir.name

    metrics = {
        "youtube_url": youtube_url,
        "run_slug": run_slug,
        **stats,
        **script_context,
    }

    tmp = metrics_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, metrics_path)

    print(f"[OK] Views: {stats.get('view_count', 0):,}")
    print(f"[OK] Likes: {stats.get('like_count', 0):,}")
    print(f"[OK] Comments: {stats.get('comment_count', 0):,}")
    print(f"[DONE] Metrics → {metrics_path}")

    # Sync to Supabase
    if sync_to_supabase(metrics, run_slug):
        print("[SUPABASE] Metrics synced for learning loop")
    else:
        print("[SUPABASE] Sync skipped (not configured or failed)")


if __name__ == "__main__":
    main()
