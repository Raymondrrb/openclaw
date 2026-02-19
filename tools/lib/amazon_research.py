"""Amazon product research — data types, validation, and products.json builder.

The OpenClaw agent handles browser interaction (searching Amazon, grabbing
Site Stripe short links). This module provides the data contract and
file formatting for the rest of the pipeline.

Stdlib only — no external deps.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from tools.lib.common import now_iso, project_root


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VIDEOS_BASE = project_root() / "artifacts" / "videos"
TOP_N_DEFAULT = 5

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class AmazonProduct:
    """A single Amazon product for the pipeline."""
    rank: int = 0
    name: str = ""
    price: str = ""
    rating: str = ""
    reviews_count: str = ""
    amazon_url: str = ""           # clean product URL
    affiliate_url: str = ""        # amzn.to short link (Site Stripe) preferred
    image_url: str = ""
    benefits: list[str] = field(default_factory=list)
    positioning: str = ""          # e.g. "budget pick", "best overall"
    target_audience: str = ""
    downside: str = ""
    asin: str = ""


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def extract_asin(url: str) -> str:
    """Extract ASIN from an Amazon product URL."""
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
    return match.group(1) if match else ""


def clean_amazon_url(url: str) -> str:
    """Clean an Amazon URL to just the canonical product page."""
    asin = extract_asin(url)
    if asin:
        return f"https://www.amazon.com/dp/{asin}"
    return url


def make_tag_url(url: str, tag: str) -> str:
    """Fallback: add ?tag= when Site Stripe is unavailable."""
    if not tag:
        return url
    asin = extract_asin(url)
    if asin:
        return f"https://www.amazon.com/dp/{asin}?tag={tag}"
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}tag={tag}"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


_ACCESSORY_KEYWORDS = {
    "replacement", "accessories", "accessory", "compatible with",
    "kit for", "pack of", "pcs for", "parts for", "filter for",
    "brush for", "pad for", "bag for", "case for", "cover for",
    "charger for", "cable for", "mount for", "stand for",
    "refill", "cartridge", "spare",
}


def _parse_price(price_str: str) -> float:
    """Parse a price string like '$26.59' into a float. Returns 0 on failure."""
    if not price_str:
        return 0.0
    cleaned = re.sub(r"[^\d.]", "", price_str)
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def validate_products(products: list[AmazonProduct]) -> list[str]:
    """Validate a list of products for pipeline readiness.

    Checks: basic fields, accessory detection, price anomalies,
    duplicate evidence, and data quality.
    """
    errors: list[str] = []

    if not products:
        errors.append("No products provided")
        return errors

    ranks = [p.rank for p in products]
    if len(ranks) != len(set(ranks)):
        errors.append("Duplicate ranks found")

    # Collect prices for median calculation
    prices = [_parse_price(p.price) for p in products if _parse_price(p.price) > 0]
    median_price = sorted(prices)[len(prices) // 2] if prices else 0.0

    # Collect all benefits for duplication check
    all_benefits: dict[str, list[int]] = {}

    for p in products:
        prefix = f"Rank {p.rank} ({p.name})"

        # --- Basic field checks ---
        if not p.name:
            errors.append(f"Rank {p.rank}: missing name")
        if not p.affiliate_url and not p.amazon_url:
            errors.append(f"{prefix}: missing URL (need affiliate_url or amazon_url)")
        if p.rank < 1:
            errors.append(f"Product '{p.name}': rank must be >= 1")

        # --- Accessory detection ---
        name_lower = p.name.lower()
        title_lower = name_lower  # name is what we have in the data model
        for kw in _ACCESSORY_KEYWORDS:
            if kw in title_lower:
                errors.append(
                    f"{prefix}: LIKELY ACCESSORIES — name contains '{kw}'. "
                    f"Must be a standalone product, not parts/accessories."
                )
                break

        # --- Price anomaly detection ---
        price_val = _parse_price(p.price)
        if price_val > 0 and median_price > 0:
            if price_val < median_price * 0.3:
                errors.append(
                    f"{prefix}: PRICE ANOMALY — ${price_val:.2f} is <30% of "
                    f"category median ${median_price:.2f}. Likely accessories or wrong ASIN."
                )

        # --- Downside required ---
        if not p.downside or len(p.downside.strip()) < 10:
            errors.append(f"{prefix}: missing or too short downside (every product needs honest limitations)")

        # --- Benefit uniqueness tracking ---
        for b in p.benefits:
            b_stripped = b.strip()
            if len(b_stripped) > 20:  # Skip trivially short benefits
                all_benefits.setdefault(b_stripped, []).append(p.rank)

    # --- Duplicate evidence check ---
    for benefit_text, used_by_ranks in all_benefits.items():
        if len(used_by_ranks) > 1:
            rank_list = ", ".join(str(r) for r in used_by_ranks)
            snippet = benefit_text[:80] + "..." if len(benefit_text) > 80 else benefit_text
            errors.append(
                f"DUPLICATE EVIDENCE: same benefit text used by ranks [{rank_list}]: "
                f'"{snippet}"'
            )

    return errors


# ---------------------------------------------------------------------------
# Save / Load
# ---------------------------------------------------------------------------


def save_products_json(
    products: list[AmazonProduct],
    output_path: Path,
    keyword: str = "",
) -> Path:
    """Save products list as pipeline-ready products.json."""
    data = []
    for p in products:
        entry = {
            "rank": p.rank,
            "name": p.name,
            "positioning": p.positioning,
            "benefits": p.benefits,
            "target_audience": p.target_audience,
            "downside": p.downside,
            "amazon_url": p.affiliate_url or p.amazon_url,
            "price": p.price,
            "rating": p.rating,
            "reviews_count": p.reviews_count,
            "image_url": p.image_url,
            "asin": p.asin,
        }
        data.append(entry)

    wrapper = {
        "keyword": keyword,
        "generated_at": now_iso(),
        "products": data,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(wrapper, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def load_products_json(path: Path) -> list[AmazonProduct]:
    """Load products from a products.json file."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("products", raw) if isinstance(raw, dict) else raw

    products = []
    for entry in items:
        products.append(AmazonProduct(
            rank=entry.get("rank", 0),
            name=entry.get("name", ""),
            price=entry.get("price", ""),
            rating=entry.get("rating", ""),
            reviews_count=entry.get("reviews_count", ""),
            amazon_url=entry.get("amazon_url", ""),
            affiliate_url=entry.get("affiliate_url", ""),
            image_url=entry.get("image_url", ""),
            benefits=entry.get("benefits", []),
            positioning=entry.get("positioning", ""),
            target_audience=entry.get("target_audience", ""),
            downside=entry.get("downside", ""),
            asin=entry.get("asin", ""),
        ))

    return products
