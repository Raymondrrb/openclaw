#!/usr/bin/env python3
"""Fetch Brave Search results (web or news) for a single query."""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from lib.common import load_env_file, save_json
from lib.url_safety import check_items, sanitize_text

API_BASE = "https://api.search.brave.com/res/v1"
DEFAULT_ENV_PATH = os.path.expanduser("~/.config/newproject/brave.env")

# Product-signal keywords — presence in title/description boosts mentionScore.
PRODUCT_KEYWORDS = {
    "best", "top", "review", "rating", "ranked", "compared", "comparison",
    "vs", "upgrade", "pick", "recommend", "winner", "budget", "premium",
    "affordable", "deal", "sale", "discount", "new", "launch", "release",
    "trending", "popular", "favorite", "must-have", "worth",
}


def api_get(endpoint, params, api_key):
    """GET request to the Brave Search API."""
    query = urllib.parse.urlencode(params)
    url = f"{API_BASE}/{endpoint}?{query}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    })
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
        # Handle gzip if server honors Accept-Encoding
        if resp.headers.get("Content-Encoding") == "gzip":
            import gzip
            data = gzip.decompress(data)
        return json.loads(data.decode("utf-8"))


def compute_mention_score(title, description):
    """Count product-related keyword hits in title + description."""
    text = f"{title} {description}".lower()
    tokens = set(re.findall(r"[a-z0-9\-]+", text))
    return sum(1.0 for kw in PRODUCT_KEYWORDS if kw in tokens)


def extract_domain(url):
    """Pull the domain from a URL."""
    if not url:
        return ""
    try:
        return urllib.parse.urlparse(url).netloc
    except Exception:
        return ""


def parse_results(raw, search_type):
    """Normalize Brave API response into our standard item list."""
    items = []
    if search_type == "web":
        for r in raw.get("web", {}).get("results", []):
            title = r.get("title", "")
            desc = r.get("description", "")
            items.append({
                "title": title,
                "url": r.get("url", ""),
                "description": desc,
                "age": r.get("age", ""),
                "domain": extract_domain(r.get("url", "")),
                "mentionScore": compute_mention_score(title, desc),
            })
    elif search_type == "news":
        for r in raw.get("results", []):
            title = r.get("title", "")
            desc = r.get("description", "")
            items.append({
                "title": title,
                "url": r.get("url", ""),
                "description": desc,
                "age": r.get("age", ""),
                "domain": extract_domain(r.get("url", "")),
                "mentionScore": compute_mention_score(title, desc),
            })
    items.sort(key=lambda x: x["mentionScore"], reverse=True)
    return items


def brave_search(query, search_type, region, freshness, count, api_key):
    """Run a single Brave search and return the structured output dict."""
    endpoint = "web/search" if search_type == "web" else "news/search"
    params = {
        "q": query,
        "country": region,
        "freshness": freshness,
        "count": count,
    }
    raw = api_get(endpoint, params, api_key)
    items = parse_results(raw, search_type)

    # Sanitize and flag unsafe URLs/text (homograph attacks, invisible chars)
    items, safety_flags = check_items(items)

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    result = {
        "source": "brave",
        "searchType": search_type,
        "query": query,
        "region": region,
        "freshness": freshness,
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "count": len(items),
        "items": items,
    }
    if safety_flags:
        result["safetyFlags"] = safety_flags
    return result


def parse_args():
    p = argparse.ArgumentParser(description="Fetch Brave Search results (web or news).")
    p.add_argument("--query", required=True, help="Search query")
    p.add_argument("--type", default="web", choices=["web", "news"], help="Search type")
    p.add_argument("--region", default="US", help="Region code")
    p.add_argument("--freshness", default="pw", help="Freshness filter (pd=day, pw=week, pm=month)")
    p.add_argument("--count", type=int, default=20, help="Number of results")
    p.add_argument("--out", required=True, help="Output JSON path")
    return p.parse_args()


def main():
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        load_env_file(DEFAULT_ENV_PATH)
        api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        print("Missing BRAVE_API_KEY env var.")
        sys.exit(1)

    args = parse_args()
    result = brave_search(args.query, args.type, args.region, args.freshness, args.count, api_key)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    save_json(args.out, result)

    print(f"Wrote {result['count']} items to {args.out}")


if __name__ == "__main__":
    main()
