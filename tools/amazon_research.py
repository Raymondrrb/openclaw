#!/usr/bin/env python3
"""CLI for Amazon product research — validate and format products.json.

The OpenClaw agent handles browser interaction (searching Amazon,
grabbing Site Stripe links). This CLI validates and formats the output.

Usage:
    # Validate an existing products.json
    python3 tools/amazon_research.py --validate products.json

    # Show products summary
    python3 tools/amazon_research.py --show --video-id my-video

    # Create empty template for a new video
    python3 tools/amazon_research.py --template --video-id my-video --keyword "your niche"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.common import load_env_file, project_root
from tools.lib.amazon_research import (
    VIDEOS_BASE,
    AmazonProduct,
    load_products_json,
    save_products_json,
    validate_products,
)


def cmd_validate(path: Path) -> int:
    """Validate a products.json file."""
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    products = load_products_json(path)
    errors = validate_products(products)

    if errors:
        print(f"Validation errors in {path.name}:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"Valid: {len(products)} products in {path.name}")
    return 0


def cmd_show(path: Path) -> int:
    """Show products summary."""
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    products = load_products_json(path)
    if not products:
        print("No products found", file=sys.stderr)
        return 1

    raw = json.loads(path.read_text(encoding="utf-8"))
    keyword = raw.get("keyword", "?") if isinstance(raw, dict) else "?"
    generated = raw.get("generated_at", "?") if isinstance(raw, dict) else "?"

    print(f"Keyword:   {keyword}")
    print(f"Generated: {generated}")
    print(f"Products:  {len(products)}\n")

    for p in sorted(products, key=lambda x: x.rank):
        link = p.affiliate_url or p.amazon_url
        is_short = "amzn.to" in link if link else False
        link_tag = " [Site Stripe]" if is_short else (" [tag]" if link else "")

        print(f"  #{p.rank}: {p.name[:60]}")
        print(f"       Price: {p.price or '?'}  Rating: {p.rating or '?'}  Reviews: {p.reviews_count or '?'}")
        if p.positioning:
            print(f"       Positioning: {p.positioning}")
        if p.benefits:
            print(f"       Benefits: {len(p.benefits)}")
        if p.downside:
            print(f"       Downside: {p.downside[:60]}")
        print(f"       {link}{link_tag}")
        print()

    return 0


def cmd_template(video_id: str, keyword: str) -> int:
    """Create an empty products.json template."""
    output_path = VIDEOS_BASE / video_id / "products.json"
    if output_path.is_file():
        print(f"Already exists: {output_path}")
        print("Use --validate or --show to inspect it")
        return 1

    products = [
        AmazonProduct(rank=i, positioning="best overall" if i == 1 else "")
        for i in range(5, 0, -1)
    ]

    save_products_json(products, output_path, keyword=keyword)
    print(f"Template created: {output_path}")
    print(f"Fill in product data, then validate with:")
    print(f"  python3 tools/amazon_research.py --validate {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Amazon product research — validate and format products.json"
    )
    parser.add_argument("--validate", default=None, help="Validate a products.json file")
    parser.add_argument("--show", action="store_true", help="Show products summary")
    parser.add_argument("--template", action="store_true", help="Create empty template")
    parser.add_argument("--video-id", default="", help="Video project identifier")
    parser.add_argument("--keyword", default="", help="Product niche keyword")
    args = parser.parse_args()

    load_env_file(project_root() / ".env")

    if args.validate:
        return cmd_validate(Path(args.validate))

    if args.show:
        if not args.video_id:
            print("--video-id required with --show", file=sys.stderr)
            return 2
        path = VIDEOS_BASE / args.video_id / "products.json"
        return cmd_show(path)

    if args.template:
        if not args.video_id:
            print("--video-id required with --template", file=sys.stderr)
            return 2
        return cmd_template(args.video_id, args.keyword)

    print("Specify --validate, --show, or --template", file=sys.stderr)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
