#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(__file__))
from lib.common import now_iso, save_json

BASE_DIR = os.environ.get("PROJECT_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
DEFAULT_CONFIG_PATH = os.path.join(BASE_DIR, "config", "daily_categories.json")
DEFAULT_OUT_DIR = os.path.join(BASE_DIR, "reports", "market")


def parse_args():
    p = argparse.ArgumentParser(description="Pick a single category-of-the-day for the pipeline (rotation).")
    p.add_argument("--date", default=dt.date.today().isoformat(), help="Date in YYYY-MM-DD (or TODAY)")
    p.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to daily category config JSON")
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="Output directory")
    return p.parse_args()


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def pick_category(date_obj: dt.date, categories: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not categories:
        raise ValueError("No categories found in config.")
    # Deterministic daily rotation (stable + easy to debug).
    idx = date_obj.toordinal() % len(categories)
    return categories[idx]


def main():
    args = parse_args()
    date_str = str(args.date).strip()
    if date_str.upper() == "TODAY":
        date_obj = dt.date.today()
        date_str = date_obj.isoformat()
    else:
        date_obj = dt.date.fromisoformat(date_str)

    cfg = load_config(args.config)
    categories = cfg.get("categories", []) or []
    picked = pick_category(date_obj, categories)

    payload = {
        "date": date_str,
        "pickedAt": now_iso(),
        "policy": cfg.get("policy", {}),
        "category": picked,
        "rotation": {
            "strategy": "date.toordinal() % len(categories)",
            "index": date_obj.toordinal() % max(len(categories), 1),
            "count": len(categories),
        },
    }

    os.makedirs(args.out_dir, exist_ok=True)
    out_json = os.path.join(args.out_dir, f"{date_str}_category_of_day.json")
    save_json(out_json, payload)

    out_md = os.path.join(args.out_dir, f"{date_str}_category_of_day.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(f"# Category of the Day — {date_str}\n\n")
        f.write(f"- Picked at (UTC): {payload['pickedAt']}\n")
        f.write(f"- Category: **{picked.get('label', picked.get('slug', 'unknown'))}**\n")
        f.write(f"- Slug: `{picked.get('slug', '')}`\n")
        amazon = picked.get("amazon", {}) or {}
        if amazon:
            f.write("\n## Amazon (starting points)\n")
            for k in ("bestSellersUrl", "newReleasesUrl", "moversUrl", "searchUrl"):
                if amazon.get(k):
                    f.write(f"- {k}: {amazon[k]}\n")

    print(out_json)
    print(out_md)


if __name__ == "__main__":
    main()

