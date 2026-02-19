#!/usr/bin/env python3
"""
YouTube Channel → CSV Exporter (with duration, likes, comments)

Usage:
    python3 tools/youtube_channel_to_csv.py
    python3 tools/youtube_channel_to_csv.py --channel-id UCMiJRAwDNSNzuYeN2uWa0pA
    python3 tools/youtube_channel_to_csv.py --channel-id UCMiJRAwDNSNzuYeN2uWa0pA --limit 100

Requires: pip install requests pandas
API key: set YOUTUBE_API_KEY env var or in ~/.config/newproject/youtube.env
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from lib.common import load_env_file

try:
    import requests
except Exception:  # pragma: no cover - optional runtime dependency
    requests = None

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional runtime dependency
    pd = None

API_BASE = "https://www.googleapis.com/youtube/v3"
DEFAULT_ENV_PATH = os.path.expanduser("~/.config/newproject/youtube.env")
MAX_RETRIES = 5


def youtube_get(url, params):
    """GET with exponential backoff for 429/5xx."""
    if requests is None:
        raise RuntimeError("Missing dependency: requests. Install with `pip install requests`.")
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503):
                wait = 2 ** attempt
                print(f"  Retry {attempt + 1}/{MAX_RETRIES} (HTTP {resp.status_code}), waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            wait = 2 ** attempt
            print(f"  Connection error, retry {attempt + 1}/{MAX_RETRIES}, waiting {wait}s...")
            time.sleep(wait)
    raise RuntimeError(f"Failed after {MAX_RETRIES} retries: {url}")


def parse_iso8601_duration_to_seconds(d):
    """Parse ISO 8601 duration (PT#H#M#S) → total seconds."""
    if not d:
        return 0
    hours = minutes = seconds = 0
    num = ""
    for ch in d:
        if ch.isdigit():
            num += ch
        elif ch == "H":
            hours = int(num or 0)
            num = ""
        elif ch == "M":
            minutes = int(num or 0)
            num = ""
        elif ch == "S":
            seconds = int(num or 0)
            num = ""
    return hours * 3600 + minutes * 60 + seconds


def seconds_to_hms(sec):
    """Format seconds to hh:mm:ss."""
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def get_uploads_playlist(channel_id, api_key):
    data = youtube_get(f"{API_BASE}/channels", {
        "part": "contentDetails,snippet,statistics",
        "id": channel_id,
        "key": api_key,
    })
    if not data.get("items"):
        raise ValueError(f"Channel not found: {channel_id}")
    item = data["items"][0]
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    content = item.get("contentDetails", {})
    playlists = content.get("relatedPlaylists", {})
    print(f"Channel: {snippet.get('title', 'Unknown')}")
    print(f"Subscribers: {int(stats.get('subscriberCount', 0)):,}")
    print(f"Total videos: {int(stats.get('videoCount', 0)):,}")
    uploads = playlists.get("uploads", "")
    if not uploads:
        raise ValueError(f"No uploads playlist found for channel: {channel_id}")
    return uploads


def get_video_ids(playlist_id, api_key, limit=0):
    """Fetch all video IDs + snippet from uploads playlist."""
    videos = []
    next_page = None

    while True:
        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": api_key,
        }
        if next_page:
            params["pageToken"] = next_page

        data = youtube_get(f"{API_BASE}/playlistItems", params)

        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            resource_id = snippet.get("resourceId", {})
            vid = resource_id.get("videoId")
            if not vid:
                continue
            title = snippet.get("title", "")
            published = snippet.get("publishedAt", "")
            videos.append({"videoId": vid, "title": title, "publishedAt": published})

        next_page = data.get("nextPageToken")
        if not next_page:
            break
        if limit and len(videos) >= limit:
            break
        time.sleep(0.1)

    if limit:
        videos = videos[:limit]
    return videos


def enrich_with_stats(videos, api_key):
    """Batch fetch stats + duration (50 IDs per request)."""
    id_list = [v["videoId"] for v in videos]
    details = {}

    for i in range(0, len(id_list), 50):
        batch = id_list[i:i + 50]
        data = youtube_get(f"{API_BASE}/videos", {
            "part": "statistics,contentDetails",
            "id": ",".join(batch),
            "key": api_key,
        })
        for item in data.get("items", []):
            vid = item["id"]
            stats = item.get("statistics", {})
            duration_iso = item.get("contentDetails", {}).get("duration", "PT0S")
            duration_sec = parse_iso8601_duration_to_seconds(duration_iso)
            details[vid] = {
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "duration_iso": duration_iso,
                "duration_seconds": duration_sec,
                "duration_hms": seconds_to_hms(duration_sec),
            }
        time.sleep(0.1)

    for v in videos:
        d = details.get(v["videoId"], {})
        v["views"] = d.get("views", 0)
        v["likes"] = d.get("likes", 0)
        v["comments"] = d.get("comments", 0)
        v["duration_iso"] = d.get("duration_iso", "PT0S")
        v["duration_seconds"] = d.get("duration_seconds", 0)
        v["duration_hms"] = d.get("duration_hms", "00:00:00")
        v["url"] = f"https://youtube.com/watch?v={v['videoId']}"

    return videos


def print_summary(df):
    """Print analysis summary."""
    print(f"\n{'='*50}")
    print(f"SUMMARY")
    print(f"{'='*50}")
    print(f"Total videos exported: {len(df)}")
    print(f"Newest: {df['publishedAt'].max()}")
    print(f"Oldest: {df['publishedAt'].min()}")
    print(f"Avg views: {df['views'].mean():,.0f}")
    print(f"Median views: {df['views'].median():,.0f}")
    print(f"Max views: {df['views'].max():,}")

    with_likes = df[df["likes"] > 0]
    if len(with_likes) > 0:
        like_ratio = (with_likes["likes"] / with_likes["views"].replace(0, 1)) * 100
        print(f"Avg like ratio: {like_ratio.mean():.2f}%")

    print(f"Avg duration: {df['duration_seconds'].mean() / 60:.1f} min")
    print(f"Avg comments: {df['comments'].mean():,.0f}")
    print(f"{'='*50}")


def main():
    if pd is None or requests is None:
        missing = []
        if pd is None:
            missing.append("pandas")
        if requests is None:
            missing.append("requests")
        print(f"Missing dependency: {', '.join(missing)}. Install with `pip install {' '.join(missing)}`.")
        sys.exit(1)

    load_env_file(DEFAULT_ENV_PATH)
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        print("Missing YOUTUBE_API_KEY. Set in env or ~/.config/newproject/youtube.env")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Export YouTube channel videos to CSV.")
    parser.add_argument("--channel-id", default="", help="YouTube channel ID (UC...)")
    parser.add_argument("--limit", type=int, default=0, help="Export only newest N videos (0 = all)")
    args = parser.parse_args()

    channel_id = args.channel_id
    if not channel_id:
        channel_id = input("Cole o Channel ID: ").strip()
    if not channel_id:
        print("Channel ID is required.")
        sys.exit(1)

    print(f"Fetching channel: {channel_id}")
    playlist_id = get_uploads_playlist(channel_id, api_key)

    print("Fetching video list...")
    videos = get_video_ids(playlist_id, api_key, limit=args.limit)
    print(f"Found {len(videos)} videos")

    print("Fetching stats + duration (batched)...")
    videos = enrich_with_stats(videos, api_key)

    # Sort by publishedAt descending
    videos.sort(key=lambda v: v["publishedAt"], reverse=True)

    # Build DataFrame with exact column order
    df = pd.DataFrame(videos, columns=[
        "title", "publishedAt", "views", "likes", "comments",
        "duration_iso", "duration_seconds", "duration_hms",
        "videoId", "url",
    ])

    # Save CSV
    out_dir = os.path.join(os.path.dirname(__file__), "..", "reports", "channels")
    os.makedirs(out_dir, exist_ok=True)
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", channel_id)
    csv_path = os.path.join(out_dir, f"channel_videos_{safe_id}.csv")
    df.to_csv(csv_path, index=False)
    print(f"\nCSV saved: {csv_path}")

    print_summary(df)


if __name__ == "__main__":
    main()
