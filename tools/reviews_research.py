#!/usr/bin/env python3
"""Reviews-first product discovery from trusted sources.

Searches whitelisted review outlets for "best <niche>" articles,
extracts product recommendations, aggregates across sources, and
produces a scored shortlist.

Usage:
    python3 tools/reviews_research.py --niche "wireless earbuds" --video-id xyz
    python3 tools/reviews_research.py --niche "wireless earbuds" --output shortlist.json

Stdlib only (+ Playwright for browser search fallback).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.common import now_iso, project_root
from tools.lib.web_search import SearchResult, web_search

# ---------------------------------------------------------------------------
# Trusted sources
# ---------------------------------------------------------------------------

TRUSTED_SOURCES = {
    "Wirecutter": {"domain": "nytimes.com/wirecutter", "weight": 3.0},
    "RTINGS": {"domain": "rtings.com", "weight": 2.5},
    "Tom's Guide": {"domain": "tomsguide.com", "weight": 2.0},
    "PCMag": {"domain": "pcmag.com", "weight": 2.0},
    "The Verge": {"domain": "theverge.com", "weight": 2.0},
    "CNET": {"domain": "cnet.com", "weight": 2.0},
    "TechRadar": {"domain": "techradar.com", "weight": 1.5},
    "Good Housekeeping": {"domain": "goodhousekeeping.com", "weight": 1.5},
    "Popular Mechanics": {"domain": "popularmechanics.com", "weight": 1.5},
}

VIDEOS_BASE = project_root() / "artifacts" / "videos"

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ProductCandidate:
    """A product mentioned by one or more trusted review sources."""
    product_name: str
    brand: str = ""
    sources: list[dict] = field(default_factory=list)  # [{source, url, label, snippet}]
    key_claims: list[str] = field(default_factory=list)
    source_count: int = 0
    evidence_score: float = 0.0
    recency_score: float = 0.0

    def __post_init__(self):
        self.source_count = len(self.sources)


@dataclass
class ResearchResult:
    niche: str
    search_queries: list[str] = field(default_factory=list)
    raw_results: list[dict] = field(default_factory=list)
    candidates: list[ProductCandidate] = field(default_factory=list)
    shortlist: list[ProductCandidate] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Search queries
# ---------------------------------------------------------------------------


def _build_queries(niche: str) -> list[tuple[str, str]]:
    """Build search queries for each trusted source. Returns (source_name, query)."""
    queries = []
    for source_name, info in TRUSTED_SOURCES.items():
        # Use the domain for targeted search
        queries.append((source_name, f"best {niche} site:{info['domain']}"))
    return queries


# ---------------------------------------------------------------------------
# Product extraction from search results
# ---------------------------------------------------------------------------

# Common product-name patterns in review article titles
# e.g. "The 7 Best Wireless Earbuds of 2026 | Reviews by Wirecutter"
# e.g. "Best Wireless Earbuds 2026: Sony WF-1000XM5, AirPods Pro..."

_BRAND_PATTERNS = [
    # "Brand Model" patterns commonly seen in tech product names
    r"\b(Sony|Apple|Samsung|Bose|Jabra|Sennheiser|JBL|Anker|Soundcore|"
    r"Google|Amazon|LG|Dyson|iRobot|Roomba|Ninja|KitchenAid|Breville|"
    r"Logitech|Razer|SteelSeries|HyperX|Corsair|Dell|ASUS|Acer|BenQ|"
    r"Philips|Braun|Oral-B|Fitbit|Garmin|Xiaomi|OnePlus|Nothing|"
    r"Beats|Audio-Technica|Shure|Blue|Elgato|Rode|Samson|"
    r"Instant Pot|Cuisinart|Hamilton Beach|Vitamix|Blendtec|"
    r"Ecobee|Ring|Nest|Arlo|Wyze|TP-Link|Netgear|Eero|"
    r"Herman Miller|Secretlab|Autonomous|FlexiSpot|"
    r"Peak Design|Osprey|Away|Samsonite|"
    r"Canon|Nikon|GoPro|DJI|Fujifilm|Insta360|"
    r"Eufy|Roborock|Dreame|Tineco|Shark|"
    r"CalDigit|Anker|Satechi|Belkin|"
    r"MSI|ViewSonic|Gigabyte|AOC|"
    r"Technics|Denon|Yamaha|Sonos|"
    r"Yeti|HydroFlask|Stanley|"
    r"1MORE|Skullcandy|Tozo|EarFun|Edifier|Moondrop|"
    r"Marshall|Bang & Olufsen|B&O|KEF|Klipsch|"
    r"Nespresso|De'Longhi|Fellow|Baratza|"
    r"Theragun|Therabody|Hyperice|"
    r"Cricut|Brother|Silhouette)\b",
]


def _extract_products_from_snippet(text: str) -> list[str]:
    """Extract product names from a search result snippet/title.

    Looks for "Brand Model" patterns — e.g. "Sony WF-1000XM5",
    "Apple AirPods Pro 2", "JBL Charge 5".
    """
    _STOP_WORDS = {
        "is", "are", "has", "was", "were", "with", "for", "and", "the",
        "our", "we", "vs", "offers", "offer", "from", "this", "that",
        "comes", "came", "gets", "delivers", "features", "brings",
        "remains", "earns", "makes", "takes", "sits", "stands",
    }

    products = []
    # Match "Brand" followed by alphanumeric model identifiers
    for pattern in _BRAND_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            brand = match.group(1)
            # Try to capture the model name after the brand
            after = text[match.end():]
            # Model is usually alphanumeric with dashes, up to ~40 chars.
            # Terminators: comma/semicolon/pipe/bullets, spaced dash " - ",
            # sentence boundary (period + space + uppercase), "...Read more".
            # Bare hyphens are NOT terminators (they appear in model names).
            model_match = re.match(
                r'\s+([\w][\w\s\-\.\/\(\)]+?)'
                r'(?:\s*[\,\;\|\·\•]'            # punctuation separators
                r'|\s+[\-\—]\s+'                  # spaced dash/em-dash
                r'|\.\s*Read\s*more'              # Google snippet truncation
                r'|\.\s+[A-Z]'                    # sentence boundary
                r'|\s+(?:' + '|'.join(_STOP_WORDS) + r')\b'  # stop words
                r'|$)',
                after,
            )
            if model_match:
                model = model_match.group(1).strip().rstrip(".")
                # Reject models that are just common words or too short
                model_lower = model.lower().strip()
                first_word = model_lower.split()[0] if model_lower.split() else ""
                if (len(model) > 1
                    and model_lower not in _STOP_WORDS
                    and model_lower not in ("a", "an", "or")
                    and first_word not in _STOP_WORDS):
                    full_name = f"{brand} {model}"
                    # Clean up
                    full_name = re.sub(r'\s+', ' ', full_name).strip()
                    if len(full_name) < 80:
                        products.append(full_name)
            else:
                # Just the brand name mentioned — skip, too vague
                pass

    return products


def _extract_brand(product_name: str) -> str:
    """Extract the brand from a product name."""
    for pattern in _BRAND_PATTERNS:
        m = re.search(pattern, product_name, re.IGNORECASE)
        if m:
            return m.group(1)
    # Fallback: first word
    parts = product_name.split()
    return parts[0] if parts else ""


def _normalize_product_name(name: str) -> str:
    """Normalize for deduplication — lowercase, strip punctuation."""
    name = name.lower().strip()
    name = re.sub(r'[^\w\s\-]', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name


# ---------------------------------------------------------------------------
# Award/position extraction
# ---------------------------------------------------------------------------


def _extract_label(title: str, snippet: str) -> str:
    """Try to extract the editorial label (best overall, best budget, etc.)."""
    text = (title + " " + snippet).lower()
    labels = [
        "best overall", "best budget", "best premium", "best value",
        "best for travel", "best for calls", "best for gaming",
        "best for running", "best for working out", "best for music",
        "editor's choice", "editors' choice", "top pick",
        "best under", "best cheap", "best affordable",
        "best noise cancelling", "best wireless",
        "best for small rooms", "best for large rooms",
        "best splurge", "upgrade pick",
    ]
    for label in labels:
        if label in text:
            return label
    return ""


# ---------------------------------------------------------------------------
# Core research flow
# ---------------------------------------------------------------------------


def search_reviews(niche: str) -> ResearchResult:
    """Search trusted sources for product recommendations.

    Returns a ResearchResult with raw results and aggregated candidates.
    """
    result = ResearchResult(niche=niche)
    queries = _build_queries(niche)

    all_product_mentions: list[dict] = []  # {product_name, brand, source, url, label, snippet}

    for source_name, query in queries:
        result.search_queries.append(query)
        print(f"  Searching: {source_name}...", file=sys.stderr)

        try:
            search_results = web_search(query, count=5)
        except Exception as exc:
            print(f"    Failed: {exc}", file=sys.stderr)
            continue

        if not search_results:
            print(f"    No results", file=sys.stderr)
            continue

        result.sources_used.append(source_name)

        for sr in search_results:
            result.raw_results.append({
                "source": source_name,
                "title": sr.title,
                "url": sr.url,
                "description": sr.description,
            })

            # Extract product names from title + description
            combined_text = f"{sr.title} {sr.description}"
            products = _extract_products_from_snippet(combined_text)

            label = _extract_label(sr.title, sr.description)

            for prod_name in products:
                brand = _extract_brand(prod_name)
                all_product_mentions.append({
                    "product_name": prod_name,
                    "brand": brand,
                    "source": source_name,
                    "url": sr.url,
                    "label": label,
                    "snippet": sr.description[:200],
                })

        print(f"    Found {len(search_results)} results, "
              f"{sum(1 for m in all_product_mentions if m['source'] == source_name)} product mentions",
              file=sys.stderr)

    # Aggregate: group by normalized product name
    product_map: dict[str, ProductCandidate] = {}

    for mention in all_product_mentions:
        key = _normalize_product_name(mention["product_name"])
        if key not in product_map:
            product_map[key] = ProductCandidate(
                product_name=mention["product_name"],
                brand=mention["brand"],
            )

        candidate = product_map[key]
        # Don't add duplicate sources
        existing_sources = {s["source"] for s in candidate.sources}
        if mention["source"] not in existing_sources:
            candidate.sources.append({
                "source": mention["source"],
                "url": mention["url"],
                "label": mention["label"],
            })
            candidate.source_count = len(candidate.sources)

        if mention["label"] and mention["label"] not in candidate.key_claims:
            candidate.key_claims.append(mention["label"])

    # Score candidates
    for candidate in product_map.values():
        # Evidence score: weighted sum of source recommendations
        for src in candidate.sources:
            source_info = TRUSTED_SOURCES.get(src["source"], {})
            candidate.evidence_score += source_info.get("weight", 1.0)

    # Sort by evidence score
    result.candidates = sorted(
        product_map.values(),
        key=lambda c: -c.evidence_score,
    )

    # Build shortlist: at least 2 sources, or 1 with "best overall"
    result.shortlist = []
    for c in result.candidates:
        if c.source_count >= 2:
            result.shortlist.append(c)
        elif c.source_count == 1 and any("best overall" in cl for cl in c.key_claims):
            result.shortlist.append(c)

    # If shortlist is too small, relax to single-source candidates
    if len(result.shortlist) < 8:
        for c in result.candidates:
            if c not in result.shortlist:
                result.shortlist.append(c)
            if len(result.shortlist) >= 15:
                break

    # Cap at 15
    result.shortlist = result.shortlist[:15]

    return result


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write_shortlist(result: ResearchResult, output_path: Path) -> None:
    """Write shortlist to JSON file."""
    data = {
        "niche": result.niche,
        "researched_at": now_iso(),
        "sources_used": result.sources_used,
        "search_queries": result.search_queries,
        "shortlist": [
            {
                "product_name": c.product_name,
                "brand": c.brand,
                "source_count": c.source_count,
                "evidence_score": round(c.evidence_score, 1),
                "sources": c.sources,
                "key_claims": c.key_claims,
            }
            for c in result.shortlist
        ],
        "total_candidates": len(result.candidates),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_research_notes(result: ResearchResult, output_path: Path) -> None:
    """Write human-readable research notes."""
    lines = [
        f"# Research Notes: {result.niche}",
        f"",
        f"**Date:** {now_iso()[:10]}",
        f"**Sources searched:** {', '.join(result.sources_used)}",
        f"**Total candidates found:** {len(result.candidates)}",
        f"**Shortlisted:** {len(result.shortlist)}",
        "",
        "## Shortlisted Products",
        "",
    ]

    for i, c in enumerate(result.shortlist, 1):
        sources_str = ", ".join(s["source"] for s in c.sources)
        claims_str = ", ".join(c.key_claims) if c.key_claims else "-"
        lines.append(f"### {i}. {c.product_name}")
        lines.append(f"- **Brand:** {c.brand}")
        lines.append(f"- **Sources ({c.source_count}):** {sources_str}")
        lines.append(f"- **Evidence score:** {c.evidence_score:.1f}")
        lines.append(f"- **Claims:** {claims_str}")
        for s in c.sources:
            lines.append(f"- [{s['source']}]({s['url']})")
        lines.append("")

    # Rejected candidates
    rejected = [c for c in result.candidates if c not in result.shortlist]
    if rejected:
        lines.append("## Rejected Candidates")
        lines.append("")
        for c in rejected[:10]:
            sources_str = ", ".join(s["source"] for s in c.sources)
            lines.append(f"- **{c.product_name}** ({sources_str}) — evidence {c.evidence_score:.1f}")
        if len(rejected) > 10:
            lines.append(f"- ... and {len(rejected) - 10} more")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Reviews-first product discovery")
    parser.add_argument("--niche", required=True, help="Product niche to research")
    parser.add_argument("--video-id", default="", help="Video ID (writes to video folder)")
    parser.add_argument("--output", default="", help="Output path for shortlist JSON")
    args = parser.parse_args()

    print(f"Researching: {args.niche}")
    print(f"Sources: {len(TRUSTED_SOURCES)}")
    print()

    result = search_reviews(args.niche)

    print(f"\nResults:")
    print(f"  Sources searched: {len(result.sources_used)}")
    print(f"  Total candidates: {len(result.candidates)}")
    print(f"  Shortlisted:      {len(result.shortlist)}")
    print()

    for i, c in enumerate(result.shortlist, 1):
        sources = ", ".join(s["source"] for s in c.sources)
        print(f"  {i:2d}. {c.product_name:<50s} [{sources}] (score: {c.evidence_score:.1f})")

    # Write outputs
    if args.video_id:
        base = VIDEOS_BASE / args.video_id / "inputs"
        shortlist_path = base / "shortlist.json"
        notes_path = base / "research_notes.md"
    elif args.output:
        shortlist_path = Path(args.output)
        notes_path = shortlist_path.with_name("research_notes.md")
    else:
        shortlist_path = project_root() / "data" / "shortlist.json"
        notes_path = project_root() / "data" / "research_notes.md"

    write_shortlist(result, shortlist_path)
    write_research_notes(result, notes_path)
    print(f"\nWrote {shortlist_path}")
    print(f"Wrote {notes_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
