#!/usr/bin/env python3
"""Extract all videos from a YouTube channel → CSV + JSON for agent analysis.

Usage:
    python3 tools/youtube_channel_analyzer.py --channel-id UC_x5XG1OV2P6uZZ5FSM9Ttw
    python3 tools/youtube_channel_analyzer.py --handle @mkbhd
    python3 tools/youtube_channel_analyzer.py --handle @mkbhd --top 50 --min-views 100000
    python3 tools/youtube_channel_analyzer.py --handle @mkbhd --category "review|top|best"
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from lib.common import iso8601_duration_to_seconds, load_env_file, now_iso, save_json

API_BASE = "https://www.googleapis.com/youtube/v3/"
DEFAULT_ENV_PATH = os.path.expanduser("~/.config/newproject/youtube.env")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports", "channels")


def api_get(endpoint, params, api_key):
    params["key"] = api_key
    query = urllib.parse.urlencode(params)
    url = f"{API_BASE}{endpoint}?{query}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def resolve_channel_id(handle_or_id, api_key):
    """Resolve @handle or channel URL to channel ID."""
    if handle_or_id.startswith("UC") and len(handle_or_id) == 24:
        return handle_or_id

    handle = handle_or_id.lstrip("@")
    # Try forHandle first (YouTube Data API v3)
    try:
        data = api_get("channels", {"part": "id", "forHandle": handle}, api_key)
        if data.get("items"):
            return data["items"][0]["id"]
    except Exception:
        pass

    # Fallback: search for channel
    data = api_get("search", {
        "part": "snippet",
        "q": handle,
        "type": "channel",
        "maxResults": 1,
    }, api_key)
    if data.get("items"):
        snippet = data["items"][0].get("snippet", {})
        if "channelId" in snippet:
            return snippet["channelId"]

    raise ValueError(f"Could not resolve channel: {handle_or_id}")


def get_channel_info(channel_id, api_key):
    data = api_get("channels", {
        "part": "snippet,contentDetails,statistics",
        "id": channel_id,
    }, api_key)
    if not data.get("items"):
        raise ValueError(f"Channel not found: {channel_id}")
    item = data["items"][0]
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    content = item.get("contentDetails", {})
    playlists = content.get("relatedPlaylists", {})
    return {
        "channel_id": channel_id,
        "name": snippet.get("title", ""),
        "handle": snippet.get("customUrl", ""),
        "subscribers": int(stats.get("subscriberCount", 0)),
        "total_videos": int(stats.get("videoCount", 0)),
        "total_views": int(stats.get("viewCount", 0)),
        "uploads_playlist": playlists.get("uploads", ""),
    }


def get_all_video_ids(playlist_id, api_key, max_pages=20):
    """Get all video IDs from uploads playlist."""
    video_ids = []
    next_page = None
    page = 0

    while page < max_pages:
        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 50,
        }
        if next_page:
            params["pageToken"] = next_page

        data = api_get("playlistItems", params, api_key)

        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            resource_id = snippet.get("resourceId", {})
            vid = resource_id.get("videoId")
            if not vid:
                continue
            title = snippet.get("title", "")
            published = snippet.get("publishedAt", "")
            video_ids.append((vid, title, published))

        next_page = data.get("nextPageToken")
        if not next_page:
            break
        page += 1
        time.sleep(0.1)  # rate limit courtesy

    return video_ids


def get_video_details(video_ids, api_key):
    """Batch fetch video stats + duration (50 per request)."""
    details = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        ids_str = ",".join(batch)
        data = api_get("videos", {
            "part": "statistics,contentDetails",
            "id": ids_str,
        }, api_key)

        for item in data.get("items", []):
            vid = item.get("id", "")
            stats = item.get("statistics", {})
            content = item.get("contentDetails", {})
            duration_sec = iso8601_duration_to_seconds(
                content.get("duration", "PT0S")
            )
            details[vid] = {
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "duration_sec": duration_sec,
                "duration_min": round(duration_sec / 60, 1),
            }
        time.sleep(0.1)

    return details


def analyze_videos(videos):
    """Compute aggregate stats from video list."""
    if not videos:
        return {}

    views = [v["views"] for v in videos]
    durations = [v["duration_min"] for v in videos if v["duration_min"] > 0]

    total = len(videos)
    avg_views = sum(views) / total
    median_views = sorted(views)[total // 2]

    # Top performers (>2x average)
    top_performers = [v for v in videos if v["views"] > avg_views * 2]

    # Videos with "top" "best" "review" in title
    review_pattern = re.compile(r"(top\s*\d|best|review|vs|compared|under\s*\$)", re.I)
    review_videos = [v for v in videos if review_pattern.search(v["title"])]

    # Duration buckets
    short = [v for v in videos if v["duration_min"] <= 5]
    medium = [v for v in videos if 5 < v["duration_min"] <= 15]
    long_vids = [v for v in videos if v["duration_min"] > 15]

    def avg_v(lst):
        return int(sum(v["views"] for v in lst) / len(lst)) if lst else 0

    return {
        "total_videos": total,
        "avg_views": int(avg_views),
        "median_views": median_views,
        "max_views": max(views),
        "avg_duration_min": round(sum(durations) / len(durations), 1) if durations else 0,
        "top_performers_count": len(top_performers),
        "review_format_videos": len(review_videos),
        "review_format_avg_views": avg_v(review_videos),
        "short_videos_avg_views": avg_v(short),
        "medium_videos_avg_views": avg_v(medium),
        "long_videos_avg_views": avg_v(long_vids),
        "engagement_rate_avg": round(
            sum((v["likes"] + v["comments"]) / max(v["views"], 1) * 100 for v in videos) / total, 2
        ),
    }


def main():
    load_env_file(DEFAULT_ENV_PATH)
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        print("Missing YOUTUBE_API_KEY. Set in env or ~/.config/newproject/youtube.env")
        sys.exit(1)

    p = argparse.ArgumentParser(description="Extract YouTube channel data for analysis.")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--channel-id", help="YouTube channel ID (starts with UC)")
    group.add_argument("--handle", help="YouTube handle (@mkbhd) or channel URL")
    p.add_argument("--top", type=int, default=0, help="Only output top N videos by views")
    p.add_argument("--min-views", type=int, default=0, help="Filter: minimum view count")
    p.add_argument("--category", default="", help="Regex filter on title (e.g. 'review|top|best')")
    p.add_argument("--max-pages", type=int, default=20, help="Max playlist pages (50 videos each)")
    p.add_argument("--format", choices=["csv", "json", "both"], default="both", help="Output format")
    p.add_argument("--out-dir", default=OUT_DIR, help="Output directory")
    args = p.parse_args()

    # Resolve channel
    channel_id = args.channel_id or resolve_channel_id(args.handle, api_key)
    print(f"Resolving channel: {channel_id}")

    info = get_channel_info(channel_id, api_key)
    print(f"Channel: {info['name']} ({info['handle']})")
    print(f"Subscribers: {info['subscribers']:,} | Videos: {info['total_videos']:,}")

    # Fetch all videos
    print("Fetching video list...")
    raw_videos = get_all_video_ids(info["uploads_playlist"], api_key, args.max_pages)
    print(f"Found {len(raw_videos)} videos")

    # Batch fetch details
    print("Fetching video stats...")
    all_ids = [v[0] for v in raw_videos]
    details = get_video_details(all_ids, api_key)

    # Build full records
    videos = []
    for vid, title, published in raw_videos:
        d = details.get(vid, {})
        videos.append({
            "video_id": vid,
            "title": title,
            "published": published,
            "url": f"https://youtube.com/watch?v={vid}",
            "views": d.get("views", 0),
            "likes": d.get("likes", 0),
            "comments": d.get("comments", 0),
            "duration_sec": d.get("duration_sec", 0),
            "duration_min": d.get("duration_min", 0),
        })

    # Apply filters
    if args.min_views:
        videos = [v for v in videos if v["views"] >= args.min_views]
    if args.category:
        pat = re.compile(args.category, re.I)
        videos = [v for v in videos if pat.search(v["title"])]

    # Sort by views descending
    videos.sort(key=lambda v: v["views"], reverse=True)

    if args.top:
        videos = videos[:args.top]

    # Compute analytics
    stats = analyze_videos(videos)

    # Output
    os.makedirs(args.out_dir, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", info.get("name", "channel").lower()).strip("_")

    if args.format in ("csv", "both"):
        csv_path = os.path.join(args.out_dir, f"{slug}_videos.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "video_id", "title", "published", "url",
                "views", "likes", "comments", "duration_sec", "duration_min",
            ])
            writer.writeheader()
            writer.writerows(videos)
        print(f"CSV: {csv_path}")

    if args.format in ("json", "both"):
        json_path = os.path.join(args.out_dir, f"{slug}_analysis.json")
        output = {
            "channel": info,
            "extracted_at": now_iso(),
            "filters": {
                "min_views": args.min_views,
                "category": args.category,
                "top": args.top,
            },
            "stats": stats,
            "videos": videos,
        }
        save_json(json_path, output)
        print(f"JSON: {json_path}")

    # Print summary
    print(f"\n--- {info['name']} Analysis ---")
    print(f"Videos analyzed: {stats.get('total_videos', 0)}")
    print(f"Avg views: {stats.get('avg_views', 0):,}")
    print(f"Median views: {stats.get('median_views', 0):,}")
    print(f"Max views: {stats.get('max_views', 0):,}")
    print(f"Avg duration: {stats.get('avg_duration_min', 0)} min")
    print(f"Review-format videos: {stats.get('review_format_videos', 0)} (avg {stats.get('review_format_avg_views', 0):,} views)")
    print(f"Engagement rate: {stats.get('engagement_rate_avg', 0)}%")
    print(f"Best duration bucket: short={stats.get('short_videos_avg_views', 0):,} | medium={stats.get('medium_videos_avg_views', 0):,} | long={stats.get('long_videos_avg_views', 0):,}")


if __name__ == "__main__":
    main()
