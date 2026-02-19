#!/usr/bin/env python3
"""Batch runner for Brave Search trends — web + news per category."""
import json
import os
import sys
import time
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))
from lib.common import load_env_file, save_json
from brave_search import brave_search

DEFAULT_ENV_PATH = os.path.expanduser("~/.config/newproject/brave.env")


def main():
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        load_env_file(DEFAULT_ENV_PATH)
        api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        print("Missing BRAVE_API_KEY env var.")
        sys.exit(1)

    _base = os.environ.get("PROJECT_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    config_path = os.environ.get("BRAVE_CONFIG", os.path.join(_base, "config", "brave_queries.json"))
    with open(config_path, "r", encoding="utf-8") as f:
        configs = json.load(f)

    out_dir = os.path.join(_base, "reports", "trends")
    os.makedirs(out_dir, exist_ok=True)
    today = dt.date.today().isoformat()

    outputs = []
    for cfg in configs:
        slug = cfg["slug"]
        region = cfg.get("region", "US")
        freshness = cfg.get("freshness", "pw")
        count = cfg.get("count", 20)

        # Web search
        try:
            result = brave_search(cfg["web_query"], "web", region, freshness, count, api_key)
            out_path = os.path.join(out_dir, f"{slug}_{today}_brave_web.json")
            save_json(out_path, result)
            outputs.append(out_path)
            print(f"  [web]  {slug}: {result['count']} items")
        except Exception as e:
            print(f"  [web]  {slug}: ERROR — {e}")

        # Rate limit: 1 req/sec on free tier
        time.sleep(1.1)

        # News search
        try:
            result = brave_search(cfg["news_query"], "news", region, freshness, count, api_key)
            out_path = os.path.join(out_dir, f"{slug}_{today}_brave_news.json")
            save_json(out_path, result)
            outputs.append(out_path)
            print(f"  [news] {slug}: {result['count']} items")
        except Exception as e:
            print(f"  [news] {slug}: ERROR — {e}")

        time.sleep(1.1)

    if outputs:
        print(f"\nWrote {len(outputs)} files to {out_dir}")
    else:
        print("No outputs generated.")


if __name__ == "__main__":
    main()
