#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from lib.common import iso8601_duration_to_seconds, load_env_file, save_json

API_BASE = "https://www.googleapis.com/youtube/v3/"
DEFAULT_ENV_PATH = os.path.expanduser("~/.config/newproject/youtube.env")


def api_get(endpoint, params):
    query = urllib.parse.urlencode(params)
    url = f"{API_BASE}{endpoint}?{query}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_args():
    p = argparse.ArgumentParser(description="Fetch trending YouTube videos by query.")
    p.add_argument("--query", required=True, help="Search query, e.g., 'open ear earbuds review'")
    p.add_argument("--region", default="US", help="Region code, e.g., US")
    p.add_argument("--category-id", default="", help="Video category ID (optional)")
    p.add_argument("--published-hours", type=int, default=48, help="Lookback window in hours")
    p.add_argument("--max-results", type=int, default=25, help="Max results from search")
    p.add_argument("--duration", default="any", choices=["any", "short", "medium", "long"], help="Video duration filter")
    p.add_argument("--out", required=True, help="Output JSON path")
    return p.parse_args()


def main():
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        load_env_file(DEFAULT_ENV_PATH)
        api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        print("Missing YOUTUBE_API_KEY env var.")
        sys.exit(1)

    args = parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    published_after = (now - dt.timedelta(hours=args.published_hours)).isoformat("T") + "Z"

    search_params = {
        "key": api_key,
        "part": "snippet",
        "type": "video",
        "q": args.query,
        "order": "viewCount",
        "publishedAfter": published_after,
        "maxResults": args.max_results,
        "regionCode": args.region,
        "relevanceLanguage": "en",
        "videoDuration": args.duration,
    }
    if args.category_id:
        search_params["videoCategoryId"] = args.category_id

    search = api_get("search", search_params)
    video_ids = [
        item["id"]["videoId"]
        for item in search.get("items", [])
        if isinstance(item.get("id"), dict) and "videoId" in item["id"]
    ]
    if not video_ids:
        print("No videos found.")
        sys.exit(0)

    details = api_get(
        "videos",
        {
            "key": api_key,
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(video_ids),
            "maxResults": len(video_ids),
        },
    )

    rows = []
    for item in details.get("items", []):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        content = item.get("contentDetails", {})
        published_at = snippet.get("publishedAt")
        if not published_at:
            continue
        published_dt = dt.datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        age_hours = max((now.replace(tzinfo=dt.timezone.utc) - published_dt).total_seconds() / 3600, 0.1)

        view_count = int(stats.get("viewCount", 0))
        like_count = int(stats.get("likeCount", 0)) if "likeCount" in stats else None
        comment_count = int(stats.get("commentCount", 0)) if "commentCount" in stats else None

        duration_sec = iso8601_duration_to_seconds(content.get("duration", "PT0S"))
        views_per_hour = view_count / age_hours
        like_rate = (like_count / view_count) if like_count and view_count else None

        rows.append(
            {
                "videoId": item.get("id"),
                "title": snippet.get("title"),
                "channelTitle": snippet.get("channelTitle"),
                "publishedAt": published_at,
                "url": f"https://www.youtube.com/watch?v={item.get('id')}",
                "viewCount": view_count,
                "likeCount": like_count,
                "commentCount": comment_count,
                "durationSec": duration_sec,
                "viewsPerHour": round(views_per_hour, 2),
                "likeRate": round(like_rate, 4) if like_rate is not None else None,
            }
        )

    rows.sort(key=lambda r: r["viewsPerHour"], reverse=True)

    out = {
        "query": args.query,
        "region": args.region,
        "categoryId": args.category_id,
        "publishedAfter": published_after,
        "generatedAt": now.isoformat() + "Z",
        "count": len(rows),
        "items": rows,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    save_json(args.out, out)

    print(f"Wrote {len(rows)} items to {args.out}")


if __name__ == "__main__":
    main()
