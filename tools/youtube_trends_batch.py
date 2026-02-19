#!/usr/bin/env python3
import json
import os
import sys
import datetime as dt
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


def fetch_trends(cfg, out_dir):
    now = dt.datetime.now(dt.timezone.utc)
    published_after = (now - dt.timedelta(hours=cfg["published_hours"])).isoformat("T") + "Z"

    search_params = {
        "key": os.environ["YOUTUBE_API_KEY"],
        "part": "snippet",
        "type": "video",
        "q": cfg["query"],
        "order": "viewCount",
        "publishedAfter": published_after,
        "maxResults": cfg["max_results"],
        "regionCode": cfg["region"],
        "relevanceLanguage": "en",
        "videoDuration": cfg["duration"],
    }
    if cfg.get("category_id"):
        search_params["videoCategoryId"] = cfg["category_id"]

    search = api_get("search", search_params)
    video_ids = [
        item["id"]["videoId"]
        for item in search.get("items", [])
        if isinstance(item.get("id"), dict) and "videoId" in item["id"]
    ]
    if not video_ids:
        return None

    details = api_get(
        "videos",
        {
            "key": os.environ["YOUTUBE_API_KEY"],
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
        "query": cfg["query"],
        "region": cfg["region"],
        "categoryId": cfg.get("category_id", ""),
        "publishedAfter": published_after,
        "generatedAt": now.isoformat() + "Z",
        "count": len(rows),
        "items": rows,
    }

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{cfg['slug']}_{now.date().isoformat()}.json")
    save_json(out_path, out)
    return out_path


def main():
    if "YOUTUBE_API_KEY" not in os.environ:
        load_env_file(DEFAULT_ENV_PATH)

    if "YOUTUBE_API_KEY" not in os.environ:
        print("Missing YOUTUBE_API_KEY env var.")
        sys.exit(1)

    _base = os.environ.get("PROJECT_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    config_path = os.environ.get("TREND_CONFIG", os.path.join(_base, "config", "trend_queries.json"))
    with open(config_path, "r", encoding="utf-8") as f:
        configs = json.load(f)

    out_dir = os.path.join(_base, "reports", "trends")
    outputs = []
    for cfg in configs:
        out = fetch_trends(cfg, out_dir)
        if out:
            outputs.append(out)

    if outputs:
        print("Wrote:")
        for path in outputs:
            print(path)
    else:
        print("No outputs generated.")


if __name__ == "__main__":
    main()
