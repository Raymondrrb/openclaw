#!/usr/bin/env python3
"""Evidence-first research agent — actually browses review pages.

Opens real review articles from trusted sources, reads the content,
extracts product picks with evidence, aggregates across sources,
and produces a structured research report + shortlist.

This is NOT a search-snippet scraper. It opens pages and reads them.

Usage (RUN mode — produces real artifacts):
    python3 tools/research_agent.py --video-id xyz --niche "wireless earbuds"

Stdlib only (+ Playwright for browser fallback).
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.common import load_env_file, now_iso, project_root
from tools.lib.page_reader import extract_headings, fetch_page_data, fetch_page_text
from tools.lib.web_search import web_search

# ---------------------------------------------------------------------------
# Trusted sources (same as reviews_research.py)
# ---------------------------------------------------------------------------

TRUSTED_SOURCES = {
    "Wirecutter": {"domain": "nytimes.com/wirecutter", "weight": 3.0},
    "RTINGS": {"domain": "rtings.com", "weight": 2.5},
    "PCMag": {"domain": "pcmag.com", "weight": 2.0},
}

# Hard restriction: only these 3 domains are allowed in research output.
_ALLOWED_DOMAINS = {"nytimes.com", "rtings.com", "pcmag.com"}

# Brand patterns for product name detection
_BRANDS = (
    r"Sony|Apple|Samsung|Bose|Jabra|Sennheiser|JBL|Anker|Soundcore|"
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
    r"CalDigit|Satechi|Belkin|"
    r"MSI|ViewSonic|Gigabyte|AOC|"
    r"Technics|Denon|Yamaha|Sonos|"
    r"Yeti|HydroFlask|Stanley|"
    r"1MORE|Skullcandy|Tozo|EarFun|Edifier|Moondrop|"
    r"Marshall|Bang & Olufsen|B&O|KEF|Klipsch|"
    r"Nespresso|De'Longhi|Fellow|Baratza|"
    r"Theragun|Therabody|Hyperice|"
    r"Cambridge Audio|Cricut|Brother|Silhouette"
)

_BRAND_RE = re.compile(rf"\b({_BRANDS})\b", re.IGNORECASE)

# Category labels to look for
_CATEGORY_LABELS = [
    "best overall", "top pick", "our pick", "editor's choice", "editors' choice",
    "best budget", "best cheap", "best affordable", "best under",
    "best premium", "best splurge", "upgrade pick",
    "best value", "best bang for the buck",
    "best for travel", "best for calls", "best for gaming",
    "best for running", "best for working out", "best for music",
    "best noise cancelling", "best wireless", "best wired",
    "best for small rooms", "best for large rooms",
    "best for iphone", "best for android",
    "runner-up", "also great",
]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ProductEvidence:
    """A product extracted from one review page with evidence."""
    product_name: str
    brand: str = ""
    category_label: str = ""     # "best overall", "best budget", etc.
    reasons: list[str] = field(default_factory=list)  # 2-4 key reasons
    reason_confidence: list[str] = field(default_factory=list)  # parallel: measured/editorial/user_reported
    downside: str = ""           # primary downside/con extracted from review
    warranty_signal: str = ""    # warranty/return info if found
    source_name: str = ""
    source_url: str = ""
    source_date: str = ""        # publication date if found
    fetch_method: str = ""       # "http" or "browser"


@dataclass
class AggregatedProduct:
    """A product with evidence from multiple sources."""
    product_name: str
    brand: str = ""
    evidence: list[ProductEvidence] = field(default_factory=list)
    source_count: int = 0
    evidence_score: float = 0.0
    primary_label: str = ""
    all_labels: list[str] = field(default_factory=list)
    all_reasons: list[str] = field(default_factory=list)
    all_downsides: list[str] = field(default_factory=list)


@dataclass
class SourceReport:
    """What we found from one review page."""
    source_name: str
    url: str
    title: str = ""
    date: str = ""
    fetch_method: str = ""
    products_found: list[ProductEvidence] = field(default_factory=list)
    blocked: bool = False
    error: str = ""


@dataclass
class ResearchReport:
    """Full research output for one niche."""
    niche: str
    date: str = ""
    sources_reviewed: list[SourceReport] = field(default_factory=list)
    aggregated: list[AggregatedProduct] = field(default_factory=list)
    shortlist: list[AggregatedProduct] = field(default_factory=list)
    rejected: list[AggregatedProduct] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 1: Find the best review article per source
# ---------------------------------------------------------------------------


# Comparison-page title patterns — only these types of pages are valid sources
_COMPARISON_TITLE_PATTERNS = [
    r"\bbest\b",
    r"\btop\s+\d+\b",
    r"\btop\s+pick",
    r"\bour\s+pick",
    r"\breview",
    r"\bcompare",
    r"\bcomparison\b",
    r"\bbuying\s+guide\b",
    r"\brated\b",
    r"\brecommend",
    r"\bpicks?\b",
    r"\bfavorite",
    r"\beditor",
]

_COMPARISON_RE = re.compile(
    "|".join(_COMPARISON_TITLE_PATTERNS), re.IGNORECASE,
)


def _is_comparison_page(title: str, url: str) -> bool:
    """Check if a search result looks like a comparison/recommendation page.

    Only comparison/review list pages are valid research sources.
    Individual product reviews, news articles, and fluff are rejected.
    """
    if not title:
        return False
    # URL-based signals: comparison pages typically have these path patterns
    url_lower = url.lower()
    url_signals = ["/best-", "/top-", "/reviews/", "/picks/",
                   "/buying-guide", "/comparison", "/vs"]
    has_url_signal = any(s in url_lower for s in url_signals)
    # Title-based signals
    has_title_signal = bool(_COMPARISON_RE.search(title))
    return has_url_signal or has_title_signal


def _find_review_articles(niche: str) -> list[tuple[str, str, str]]:
    """Search Google for comparison/review list pages — exactly 3 sources.

    COMPARISON-FIRST: Only accepts pages that are comparison/recommendation
    lists (e.g., "Best X of 2026", "Top 5 X", "Our Picks").
    Rejects individual product reviews, news articles, and fluff.

    Returns list of (source_name, url, search_title).
    """
    articles: list[tuple[str, str, str]] = []

    for source_name, info in TRUSTED_SOURCES.items():
        domain = info["domain"]
        # Target comparison/best-of pages explicitly
        query = f"best {niche} site:{domain}"

        print(f"  Searching {source_name}...", file=sys.stderr)
        try:
            results = web_search(query, count=3)
        except Exception as exc:
            print(f"    Search failed: {exc}", file=sys.stderr)
            continue

        if not results:
            print(f"    No coverage", file=sys.stderr)
            continue

        # Take up to 2 COMPARISON pages per source
        added = 0
        for r in results[:3]:
            if added >= 2:
                break
            # Enforce domain restriction
            if not any(d in r.url for d in _ALLOWED_DOMAINS):
                print(f"    SKIPPED (domain violation): {r.url}", file=sys.stderr)
                continue
            # Enforce comparison-page requirement
            if not _is_comparison_page(r.title, r.url):
                print(f"    SKIPPED (not a comparison page): {r.title[:60]}", file=sys.stderr)
                continue
            articles.append((source_name, r.url, r.title))
            print(f"    -> {r.title[:70]}", file=sys.stderr)
            added += 1
        if added == 0:
            print(f"    No comparison pages found", file=sys.stderr)

    return articles


# ---------------------------------------------------------------------------
# Step 2: Open pages and extract products
# ---------------------------------------------------------------------------


def _extract_date(text: str) -> str:
    """Try to extract a publication date from page text."""
    # Look for patterns like "Jan 16, 2026" or "January 16, 2026" or "2026-01-16"
    patterns = [
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{1,2},?\s+\d{4})",
        r"((?:Updated|Published|Reviewed)(?:\s+on)?\s*:?\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{1,2},?\s+\d{4})",
        r"(\d{4}-\d{2}-\d{2})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text[:2000], re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


# Expanded stop-words — terminate model name capture
_STOP_WORDS_PATTERN = (
    r"is|are|has|was|with|for|and|the|our|we|vs|offers?|from|this|comes|"
    r"delivers|features|best|top|most|these|here|such|than|like|rated|"
    r"that|can|will|should|which|its|they|you|it|also|very|really|quite|"
    r"do|does|did|been|being|would|could|their|your|his|her|an|as|at|by|"
    r"but|if|in|into|so|up|more|not|only|just|still|some|each|every|new|"
    r"old|any|all|review|editor|pick|choice|update|price|value|above|"
    r"below|around|over|between|sound|wireless|earbuds?|headphones?|"
    r"speakers?|budget|premium|affordable|overall|compact|portable"
)

# Regex for first-word stop check (superset of old inline list)
_FIRST_WORD_STOP = frozenset({
    "is", "are", "has", "was", "the", "a", "an", "and", "or", "for",
    "with", "best", "top", "most", "these", "here", "such", "than",
    "like", "rated", "that", "can", "will", "should", "which", "its",
    "they", "you", "it", "also", "very", "really", "quite", "do",
    "does", "did", "been", "being", "would", "could", "their", "your",
    "his", "her", "as", "at", "by", "but", "if", "in", "into", "so",
    "up", "more", "not", "only", "just", "still", "some", "each",
    "every", "new", "old", "any", "all",
})

# Phrase-like verbs — a model name should not contain these
_PHRASE_VERBS_RE = re.compile(
    r"\b(?:is|are|was|were|has|have|had|do|does|did|can|will|"
    r"would|could|should|being|been|comes?|makes?|goes?|takes?|"
    r"sounds?|feels?|looks?|works?)\b",
    re.IGNORECASE,
)


def _clean_product_name(raw_name: str, brand: str) -> str | None:
    """Validate and clean a product name. Returns None if garbage.

    Rules:
    - Model part (after brand) must be 1-5 words
    - Total name (brand + model) max 6 words
    - Model must not start with a stop-word
    - Model must not look like a phrase (verb + subject)
    - Model must contain at least 1 alphanumeric token (digit, hyphen, or uppercase)
    """
    name = re.sub(r"\s+", " ", raw_name).strip()
    if not name:
        return None

    # Strip brand prefix to get model
    model = name
    if brand and name.lower().startswith(brand.lower()):
        model = name[len(brand):].strip()

    if not model:
        return None

    words = model.split()

    # Model: 1-5 words
    if len(words) > 5:
        return None

    # Total name: max 6 words
    total_words = name.split()
    if len(total_words) > 6:
        return None

    # First word of model must not be a stop-word
    if words[0].lower() in _FIRST_WORD_STOP:
        return None

    # Must not contain phrase-like verbs (e.g., "earbuds do sound great")
    if _PHRASE_VERBS_RE.search(model):
        return None

    # Must contain at least 1 "real model" token: digit, hyphen, or uppercase letter
    has_model_token = bool(re.search(r"[0-9\-]", model)) or any(
        c.isupper() for c in model if c.isalpha()
    )
    if not has_model_token:
        return None

    return name


def _extract_products_from_headings(
    headings: list[tuple[str, str]],
    source_name: str,
    url: str,
    full_text: str,
) -> list[ProductEvidence]:
    """Heading-first product extraction from structured HTML headings.

    For each h2/h3:
    1. Strip label prefixes ("Our pick:", "Best budget:", etc.)
    2. Look for brand in _BRAND_RE
    3. Extract a clean model name directly from the heading text
    4. Find reasons/downside in the full_text near the heading
    """
    products: list[ProductEvidence] = []
    seen_names: set[str] = set()
    date = _extract_date(full_text)
    lines = full_text.splitlines()

    # Label prefixes to strip from headings
    _label_strip_re = re.compile(
        r"^(?:Our\s+pick|Top\s+pick|Best\s+(?:overall|budget|cheap|"
        r"affordable|premium|splurge|upgrade|value|for\s+\w+)|"
        r"Upgrade\s+pick|Also\s+great|Runner[- ]up|Editor'?s?\s+choice|"
        r"Editors'\s+choice)\s*[:—\-–]\s*",
        re.IGNORECASE,
    )

    for _tag, raw_heading in headings:
        # Try to detect a category label
        label = ""
        heading_lower = raw_heading.lower()
        for cat in _CATEGORY_LABELS:
            if cat in heading_lower:
                label = cat
                break

        # Strip label prefix to get the product part
        cleaned_heading = _label_strip_re.sub("", raw_heading).strip()
        if not cleaned_heading:
            continue

        # Look for brand
        bm = _BRAND_RE.search(cleaned_heading)
        if not bm:
            continue

        brand = bm.group(1)
        # Everything from brand to end of heading is the candidate name
        candidate = cleaned_heading[bm.start():]
        # Trim trailing noise: common suffix words
        candidate = re.sub(
            r"\s+(?:" + _STOP_WORDS_PATTERN + r")(?:\s.*)?$",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        candidate = re.sub(r"\s+", " ", candidate).strip().rstrip(".")

        if not candidate or candidate.lower() == brand.lower():
            continue

        cleaned = _clean_product_name(candidate, brand)
        if not cleaned:
            continue

        name_key = cleaned.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Find the heading text in full_text to locate context
        product_line = 0
        for idx, line in enumerate(lines):
            if brand in line and any(w in line for w in cleaned.split()[-2:]):
                product_line = idx
                break

        reasons = _extract_reasons(lines, product_line, brand)
        downside = _extract_downside(lines, product_line, brand)
        warranty = _extract_warranty(lines, product_line)

        from tools.lib.buyer_trust import confidence_tag
        reason_conf = [confidence_tag(r) for r in reasons]

        products.append(ProductEvidence(
            product_name=cleaned,
            brand=brand,
            category_label=label,
            reasons=reasons,
            reason_confidence=reason_conf,
            downside=downside,
            warranty_signal=warranty,
            source_name=source_name,
            source_url=url,
            source_date=date,
        ))

    return products


def _deduplicate_products(products: list[ProductEvidence]) -> list[ProductEvidence]:
    """Remove near-duplicate products, keeping the shortest (cleanest) name.

    If "Sony LinkBuds Fit" and "Sony LinkBuds Fit earbuds do" both exist,
    keep only the shorter one.
    """
    if len(products) <= 1:
        return products

    # Sort by name length (shortest first)
    sorted_products = sorted(products, key=lambda p: len(p.product_name))
    kept: list[ProductEvidence] = []
    kept_lower: list[str] = []

    for p in sorted_products:
        p_lower = p.product_name.lower()
        # Check if this is a substring of an already-kept product or vice-versa
        is_dup = False
        for kl in kept_lower:
            if kl in p_lower or p_lower in kl:
                is_dup = True
                break
        if not is_dup:
            kept.append(p)
            kept_lower.append(p_lower)

    return kept


def _extract_products_from_page(
    text: str, source_name: str, url: str
) -> list[ProductEvidence]:
    """Extract product recommendations from page text.

    Looks for:
    - Headings with category labels (Best Overall, Best Budget, etc.)
    - Brand + Model patterns
    - Surrounding context for reasons
    """
    products: list[ProductEvidence] = []
    seen_names: set[str] = set()
    date = _extract_date(text)
    lines = text.splitlines()

    # Strategy 1: Look for "Best X: Brand Model" or "Our pick: Brand Model" headings
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()

        # Check if this line has a category label
        label = ""
        for cat in _CATEGORY_LABELS:
            if cat in line_lower:
                label = cat
                break

        if not label:
            continue

        # Look for a product name in this line and the next few lines
        search_block = "\n".join(lines[i:i+5])
        brand_matches = list(_BRAND_RE.finditer(search_block))

        for bm in brand_matches:
            brand = bm.group(1)
            after = search_block[bm.end():]
            # Capture model: alphanumeric with hyphens, up to ~40 chars
            model_match = re.match(
                r"\s+([\w][\w\s\-\.\/\(\)]+?)"
                r"(?:\s*[\,\;\|\·]|\s+[\-\—]\s+|\.\s+[A-Z]"
                r"|\s+(?:" + _STOP_WORDS_PATTERN + r")\b|$)",
                after,
            )
            if model_match:
                model = model_match.group(1).strip().rstrip(".")
                if len(model) <= 1:
                    continue
                full_name = f"{brand} {model}".strip()
                full_name = re.sub(r"\s+", " ", full_name)

                cleaned = _clean_product_name(full_name, brand)
                if not cleaned:
                    continue
                full_name = cleaned
                name_key = full_name.lower()

                if name_key in seen_names or len(full_name) > 80:
                    continue
                seen_names.add(name_key)

                # Extract reasons, downside, warranty from surrounding lines
                reasons = _extract_reasons(lines, i, brand)
                downside = _extract_downside(lines, i, brand)
                warranty = _extract_warranty(lines, i)

                # Tag confidence for each reason
                from tools.lib.buyer_trust import confidence_tag
                reason_conf = [confidence_tag(r) for r in reasons]

                products.append(ProductEvidence(
                    product_name=full_name,
                    brand=brand,
                    category_label=label,
                    reasons=reasons,
                    reason_confidence=reason_conf,
                    downside=downside,
                    warranty_signal=warranty,
                    source_name=source_name,
                    source_url=url,
                    source_date=date,
                ))
                break  # one product per label line

    # Strategy 2: Scan remaining text for Brand+Model not yet captured
    # (catches products mentioned without category labels)
    for i, line in enumerate(lines):
        for bm in _BRAND_RE.finditer(line):
            brand = bm.group(1)
            after = line[bm.end():]
            model_match = re.match(
                r"\s+([\w][\w\s\-\.\/\(\)]+?)"
                r"(?:\s*[\,\;\|\·]|\s+[\-\—]\s+|\.\s+[A-Z]"
                r"|\s+(?:" + _STOP_WORDS_PATTERN + r")\b|$)",
                after,
            )
            if model_match:
                model = model_match.group(1).strip().rstrip(".")
                if len(model) <= 1:
                    continue
                full_name = f"{brand} {model}".strip()
                full_name = re.sub(r"\s+", " ", full_name)

                cleaned = _clean_product_name(full_name, brand)
                if not cleaned:
                    continue
                full_name = cleaned
                name_key = full_name.lower()

                if name_key in seen_names or len(full_name) > 80:
                    continue
                seen_names.add(name_key)

                # Try to find a nearby label
                label = ""
                nearby = "\n".join(lines[max(0, i-3):i+3]).lower()
                for cat in _CATEGORY_LABELS:
                    if cat in nearby:
                        label = cat
                        break

                reasons = _extract_reasons(lines, i, brand)
                downside = _extract_downside(lines, i, brand)
                warranty = _extract_warranty(lines, i)

                from tools.lib.buyer_trust import confidence_tag
                reason_conf = [confidence_tag(r) for r in reasons]

                products.append(ProductEvidence(
                    product_name=full_name,
                    brand=brand,
                    category_label=label,
                    reasons=reasons,
                    reason_confidence=reason_conf,
                    downside=downside,
                    warranty_signal=warranty,
                    source_name=source_name,
                    source_url=url,
                    source_date=date,
                ))

    return _deduplicate_products(products)


def _extract_reasons(lines: list[str], product_line: int, brand: str) -> list[str]:
    """Extract 2-4 key reasons from lines near a product mention."""
    reasons: list[str] = []
    # Look at the next 10 lines for reason-like sentences
    block = lines[product_line:product_line + 12]

    for line in block:
        line = line.strip()
        if not line or len(line) < 20 or len(line) > 200:
            continue
        # Skip lines that are just headings or very short
        lower = line.lower()
        # Look for sentences with quality indicators
        if any(kw in lower for kw in [
            "sound", "noise cancel", "battery", "comfort", "fit",
            "bass", "treble", "build quality", "water", "sweat",
            "price", "affordable", "premium", "value",
            "best", "great", "excellent", "impressive", "stellar",
            "durable", "lightweight", "compact", "portable",
            "microphone", "call quality", "latency", "codec",
            "anc", "transparency", "spatial audio",
            # General product qualities
            "performance", "design", "feature", "quality", "reliable",
            "powerful", "efficient", "fast", "quiet", "bright",
            "sharp", "crisp", "smooth", "sturdy", "elegant",
        ]):
            # Clean up the reason
            reason = line.strip()
            if len(reason) > 150:
                reason = reason[:147] + "..."
            if reason not in reasons:
                reasons.append(reason)
            if len(reasons) >= 4:
                break

    return reasons[:4]


_WARRANTY_EXTRACT_RE = re.compile(
    r"(\d+[- ]?year\s+(?:warranty|guarantee)|limited\s+warranty|"
    r"return\s+polic\w+|money[- ]?back\s+guarantee|replacement\s+(?:warranty|policy))",
    re.IGNORECASE,
)


def _extract_warranty(lines: list[str], product_line: int) -> str:
    """Extract warranty/return policy info from lines near a product mention."""
    block = lines[product_line:product_line + 20]
    for line in block:
        m = _WARRANTY_EXTRACT_RE.search(line)
        if m:
            return m.group(0).strip()
    return ""


_DOWNSIDE_PATTERNS = [
    r"\b(?:downside|drawback|con|weakness|negative|complaint|issue|problem|caveat|trade-?off)\b",
    r"\b(?:but|however|unfortunately|though|although|lacking|lacks|missing|doesn't|don't|can't)\b",
    r"\b(?:expensive|pricey|costly|bulky|heavy|loud|flimsy|cheap-feeling)\b",
]


def _extract_downside(lines: list[str], product_line: int, brand: str) -> str:
    """Extract a single primary downside from lines near a product mention."""
    block = lines[product_line:product_line + 15]
    for line in block:
        line = line.strip()
        if not line or len(line) < 15 or len(line) > 200:
            continue
        lower = line.lower()
        for pat in _DOWNSIDE_PATTERNS:
            if re.search(pat, lower):
                return line.strip()[:150]
    return ""


def _open_and_extract(
    source_name: str, url: str, title: str
) -> SourceReport:
    """Open a review page and extract products. The core browsing step."""
    report = SourceReport(source_name=source_name, url=url, title=title)

    print(f"\n  Opening {source_name}: {url[:80]}...", file=sys.stderr)

    text, method, raw_html = fetch_page_data(url)
    report.fetch_method = method

    if not text:
        report.blocked = True
        report.error = f"Could not fetch page (tried HTTP + browser)"
        print(f"    BLOCKED: {report.error}", file=sys.stderr)
        return report

    print(f"    Fetched via {method} ({len(text)} chars)", file=sys.stderr)

    # Extract date
    report.date = _extract_date(text)
    if report.date:
        print(f"    Date: {report.date}", file=sys.stderr)

    # Heading-first extraction when raw HTML is available
    products: list[ProductEvidence] = []
    if raw_html:
        headings = extract_headings(raw_html)
        if headings:
            products = _extract_products_from_headings(
                headings, source_name, url, text,
            )
            if len(products) >= 3:
                print(f"    Heading-first: {len(products)} products", file=sys.stderr)

    # Fallback: text-based extraction (with improved regex + validator)
    if len(products) < 3:
        products = _extract_products_from_page(text, source_name, url)

    report.products_found = products

    print(f"    Products found: {len(products)}", file=sys.stderr)
    for p in products:
        label = f" [{p.category_label}]" if p.category_label else ""
        reasons_str = f" ({len(p.reasons)} reasons)" if p.reasons else ""
        print(f"      - {p.product_name}{label}{reasons_str}", file=sys.stderr)

    # Small delay between pages to be respectful
    time.sleep(1.0)

    return report


# ---------------------------------------------------------------------------
# Step 3: Aggregate across sources
# ---------------------------------------------------------------------------


def _normalize_name(name: str) -> str:
    """Normalize for deduplication."""
    return re.sub(r"[^\w\s\-]", "", name.lower()).strip()


def _aggregate(reports: list[SourceReport]) -> list[AggregatedProduct]:
    """Merge product evidence across all sources."""
    product_map: dict[str, AggregatedProduct] = {}

    for report in reports:
        for evidence in report.products_found:
            key = _normalize_name(evidence.product_name)
            if key not in product_map:
                product_map[key] = AggregatedProduct(
                    product_name=evidence.product_name,
                    brand=evidence.brand,
                )

            agg = product_map[key]
            # Don't add duplicate source evidence
            existing_sources = {e.source_name for e in agg.evidence}
            if evidence.source_name not in existing_sources:
                agg.evidence.append(evidence)
                agg.source_count = len(agg.evidence)

            if evidence.category_label and evidence.category_label not in agg.all_labels:
                agg.all_labels.append(evidence.category_label)
                if not agg.primary_label:
                    agg.primary_label = evidence.category_label

            for r in evidence.reasons:
                if r not in agg.all_reasons:
                    agg.all_reasons.append(r)

            if evidence.downside and evidence.downside not in agg.all_downsides:
                agg.all_downsides.append(evidence.downside)

    # Score products
    for agg in product_map.values():
        for ev in agg.evidence:
            source_info = TRUSTED_SOURCES.get(ev.source_name, {})
            agg.evidence_score += source_info.get("weight", 1.0)
        # Bonus for having a category label
        if agg.primary_label:
            agg.evidence_score += 0.5

    # Sort by evidence score
    return sorted(product_map.values(), key=lambda a: -a.evidence_score)


# ---------------------------------------------------------------------------
# Step 4: Build shortlist + validate DONE
# ---------------------------------------------------------------------------


def _build_shortlist(
    aggregated: list[AggregatedProduct],
) -> tuple[list[AggregatedProduct], list[AggregatedProduct]]:
    """Build shortlist (5-7 products) and rejected list."""
    shortlist: list[AggregatedProduct] = []
    rejected: list[AggregatedProduct] = []

    for agg in aggregated:
        if agg.source_count >= 2:
            shortlist.append(agg)
        elif agg.source_count == 1 and agg.primary_label in ("best overall", "top pick", "our pick"):
            shortlist.append(agg)
        elif agg.source_count == 1 and agg.evidence_score >= 2.0:
            shortlist.append(agg)
        else:
            rejected.append(agg)

    # If shortlist too small, relax criteria
    if len(shortlist) < 5:
        for agg in rejected[:]:
            if len(shortlist) >= 7:
                break
            shortlist.append(agg)
            rejected.remove(agg)

    # Cap at 7
    if len(shortlist) > 7:
        overflow = shortlist[7:]
        shortlist = shortlist[:7]
        rejected = overflow + rejected

    return shortlist, rejected


def _validate_done(report: ResearchReport) -> list[str]:
    """Validate the DONE criteria for research stage."""
    errors = []

    # Exactly 3 sources attempted (Wirecutter, RTINGS, PCMag)
    sources_ok = [s for s in report.sources_reviewed if not s.blocked and s.products_found]
    if len(sources_ok) < 2:
        errors.append(f"Only {len(sources_ok)} sources produced results (minimum 2)")

    # Domain violation check: no foreign domains in output
    for s in report.sources_reviewed:
        if not any(d in s.url for d in _ALLOWED_DOMAINS):
            errors.append(f"Source violation – research restricted to 3 domains. Found: {s.url}")

    # At least 5 unique products mentioned
    all_products = set()
    for s in report.sources_reviewed:
        for p in s.products_found:
            all_products.add(_normalize_name(p.product_name))
    if len(all_products) < 5:
        errors.append(f"Only {len(all_products)} unique products found (minimum 5)")

    # Shortlist has 5-7 items
    if len(report.shortlist) < 5:
        errors.append(f"Shortlist has {len(report.shortlist)} items (minimum 5)")
    if len(report.shortlist) > 7:
        errors.append(f"Shortlist has {len(report.shortlist)} items (maximum 7)")

    # Every shortlisted product must have at least 1 reason/claim
    for agg in report.shortlist:
        if not agg.all_reasons:
            errors.append(f"Shortlist product '{agg.product_name}' has no evidence claims")

    # At least 3 of shortlisted must have 2+ reasons
    well_evidenced = sum(1 for agg in report.shortlist if len(agg.all_reasons) >= 2)
    if report.shortlist and well_evidenced < min(3, len(report.shortlist)):
        errors.append(f"Only {well_evidenced} shortlisted products have 2+ evidence claims (minimum 3)")

    return errors


# ---------------------------------------------------------------------------
# Step 5: Write outputs
# ---------------------------------------------------------------------------


def _write_research_report(report: ResearchReport, output_path: Path) -> None:
    """Write human-readable research_report.md."""
    lines = [
        f"# Research Report: {report.niche}",
        f"",
        f"**Date:** {report.date}",
        f"**Sources reviewed:** {len(report.sources_reviewed)}",
        f"**Sources with results:** {len([s for s in report.sources_reviewed if s.products_found])}",
        f"**Unique products found:** {len(report.aggregated)}",
        f"**Shortlisted:** {len(report.shortlist)}",
        "",
    ]

    # Validation
    if report.validation_errors:
        lines.append("## Validation Issues")
        lines.append("")
        for err in report.validation_errors:
            lines.append(f"- {err}")
        lines.append("")

    # Sources reviewed
    lines.append("## Sources Reviewed")
    lines.append("")
    for src in report.sources_reviewed:
        status = "BLOCKED" if src.blocked else f"{len(src.products_found)} products"
        method = f" (via {src.fetch_method})" if src.fetch_method else ""
        date = f" | {src.date}" if src.date else ""
        lines.append(f"### {src.source_name}{date}")
        lines.append(f"- **URL:** [{src.title or src.url}]({src.url})")
        lines.append(f"- **Status:** {status}{method}")
        if src.error:
            lines.append(f"- **Error:** {src.error}")
        for p in src.products_found:
            label = f" [{p.category_label}]" if p.category_label else ""
            lines.append(f"  - {p.product_name}{label}")
            for r in p.reasons[:2]:
                lines.append(f"    - {r}")
        lines.append("")

    # Products repeated across sources
    multi_source = [a for a in report.aggregated if a.source_count >= 2]
    if multi_source:
        lines.append("## Products Repeated Across Sources")
        lines.append("")
        for agg in multi_source:
            sources = ", ".join(e.source_name for e in agg.evidence)
            label = f" [{agg.primary_label}]" if agg.primary_label else ""
            lines.append(f"- **{agg.product_name}** ({agg.source_count} sources: {sources}){label}")
            lines.append(f"  Evidence score: {agg.evidence_score:.1f}")
        lines.append("")

    # Shortlist
    lines.append("## Shortlist (5-7)")
    lines.append("")
    for i, agg in enumerate(report.shortlist, 1):
        sources = ", ".join(e.source_name for e in agg.evidence)
        label = f" [{agg.primary_label}]" if agg.primary_label else ""
        lines.append(f"### {i}. {agg.product_name}{label}")
        lines.append(f"- **Brand:** {agg.brand}")
        lines.append(f"- **Sources ({agg.source_count}):** {sources}")
        lines.append(f"- **Evidence score:** {agg.evidence_score:.1f}")
        if agg.all_labels:
            lines.append(f"- **Labels:** {', '.join(agg.all_labels)}")
        if agg.all_reasons:
            lines.append(f"- **Key reasons:**")
            for r in agg.all_reasons[:4]:
                lines.append(f"  - {r}")
        if agg.all_downsides:
            lines.append(f"- **Downside:** {agg.all_downsides[0]}")
        for ev in agg.evidence:
            lines.append(f"- [{ev.source_name}]({ev.source_url})")
        lines.append("")

    # Rejected
    if report.rejected:
        lines.append("## Rejected Candidates and Why")
        lines.append("")
        for agg in report.rejected[:15]:
            sources = ", ".join(e.source_name for e in agg.evidence)
            reason = "single source, low weight" if agg.source_count == 1 else "low evidence score"
            if not agg.primary_label:
                reason += ", no category label"
            lines.append(f"- **{agg.product_name}** ({sources}) — {reason} (score: {agg.evidence_score:.1f})")
        if len(report.rejected) > 15:
            lines.append(f"- ... and {len(report.rejected) - 15} more")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _extract_model(product_name: str, brand: str) -> str:
    """Extract model name by stripping brand prefix."""
    if brand and product_name.lower().startswith(brand.lower()):
        model = product_name[len(brand):].strip()
        return model if model else product_name
    return product_name


def _why_in_shortlist(agg: AggregatedProduct) -> str:
    """Auto-generate 1-2 line summary explaining why this product is shortlisted."""
    parts = []
    if agg.source_count >= 2:
        source_names = ", ".join(ev.source_name for ev in agg.evidence)
        parts.append(f"Recommended by {agg.source_count} sources: {source_names}")
    elif agg.source_count == 1:
        parts.append(f"Recommended by {agg.evidence[0].source_name}")
    if agg.primary_label:
        parts.append(f"[{agg.primary_label}]")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Generic claim filter
# ---------------------------------------------------------------------------

GENERIC_CLAIMS = frozenset({
    "great sound", "high quality", "good value", "nice design",
    "comfortable", "easy to use", "looks great", "works well",
    "solid build", "good performance", "well built", "good sound",
    "nice build", "great design", "good quality", "works great",
})


def _is_generic_claim(claim: str) -> bool:
    """Check if a claim is generic filler with no attributed evidence."""
    return claim.lower().strip().rstrip(".") in GENERIC_CLAIMS


def _filter_generic_reasons(reasons: list[str]) -> list[str]:
    """Remove generic claims from a reasons list."""
    return [r for r in reasons if not _is_generic_claim(r)]


def _write_shortlist_json(report: ResearchReport, output_path: Path) -> None:
    """Write structured shortlist.json."""
    data = {
        "niche": report.niche,
        "researched_at": now_iso(),
        "date": report.date,
        "sources_reviewed": len(report.sources_reviewed),
        "sources_with_results": len([s for s in report.sources_reviewed if s.products_found]),
        "total_candidates": len(report.aggregated),
        "validation_errors": report.validation_errors,
        "shortlist": [
            {
                "product_name": agg.product_name,
                "brand": agg.brand,
                "model": _extract_model(agg.product_name, agg.brand),
                "evidence_count": agg.source_count,
                "evidence_score": round(agg.evidence_score, 1),
                "primary_label": agg.primary_label,
                "all_labels": agg.all_labels,
                "why_in_shortlist": _why_in_shortlist(agg),
                "buyer_pain_fit": "",  # populated by cluster micro-niche if available
                "pass_subcategory_gate": True,
                "evidence_by_source": {
                    ev.source_name.lower().replace(" ", "_"): {
                        "url": ev.source_url,
                        "key_claims": _filter_generic_reasons(ev.reasons[:3]),
                        "claim_confidence": ev.reason_confidence[:3] if ev.reason_confidence else [],
                        "warranty_signal": ev.warranty_signal,
                        "subcategory_proof": [ev.category_label] if ev.category_label else [],
                    }
                    for ev in agg.evidence
                },
                "sources": [
                    {
                        "name": ev.source_name,
                        "url": ev.source_url,
                        "label": ev.category_label,
                        "date": ev.source_date,
                    }
                    for ev in agg.evidence
                ],
                "reasons": _filter_generic_reasons(agg.all_reasons[:4]),
                "downside": agg.all_downsides[0] if agg.all_downsides else "",
            }
            for agg in report.shortlist
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main agent function
# ---------------------------------------------------------------------------


def run_reviews_research(
    video_id: str,
    niche: str,
    *,
    output_dir: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
    contract_path: Path | None = None,
) -> ResearchReport:
    """Execute the full evidence-first research pipeline.

    This is the AGENT — it does the work, not just scaffolding.

    Steps:
    1. Search Google for review articles from trusted sources
    2. Open each page, read content, extract products with evidence
    3. Aggregate across sources
    4. Validate DONE criteria
    5. Write outputs + notify

    Returns the ResearchReport (also writes to disk).
    """
    from tools.lib.video_paths import VideoPaths, VIDEOS_BASE

    paths = VideoPaths(video_id) if not output_dir else None
    base = output_dir or (VIDEOS_BASE / video_id / "inputs")

    report = ResearchReport(niche=niche, date=now_iso()[:10])

    # --- Step 1: Find review articles ---
    print(f"\n[research] Step 1: Finding review articles for '{niche}'...", file=sys.stderr)
    articles = _find_review_articles(niche)

    if dry_run:
        print(f"\n[DRY RUN] Would open {len(articles)} review pages:", file=sys.stderr)
        for source, url, title in articles:
            print(f"  {source}: {title[:60]} ({url[:60]})", file=sys.stderr)
        print(f"\n[DRY RUN] Then aggregate, validate, and write outputs.", file=sys.stderr)
        return report

    if not articles:
        print("[research] No review articles found!", file=sys.stderr)
        return report

    # Check: at least 2 of 3 sources must have results
    sources_found = {a[0] for a in articles}
    if len(sources_found) < 2:
        print(f"[research] ABORT: Only {len(sources_found)} source(s) have coverage. Minimum 2.", file=sys.stderr)
        report.validation_errors.append(f"Only {len(sources_found)}/3 sources have coverage (minimum 2)")
        return report

    # --- Step 2: Open each page and extract products ---
    print(f"\n[research] Step 2: Opening {len(articles)} review pages...", file=sys.stderr)
    for source_name, url, title in articles:
        # Enforce domain restriction
        if not any(d in url for d in _ALLOWED_DOMAINS):
            err = f"Source violation – research restricted to 3 domains. Blocked: {url}"
            print(f"  ABORT: {err}", file=sys.stderr)
            report.validation_errors.append(err)
            return report
        source_report = _open_and_extract(source_name, url, title)
        report.sources_reviewed.append(source_report)

    # --- Step 3: Aggregate ---
    print(f"\n[research] Step 3: Aggregating evidence...", file=sys.stderr)
    report.aggregated = _aggregate(report.sources_reviewed)

    # --- Step 3b: Subcategory gate filtering ---
    contract = None
    if contract_path and contract_path.is_file():
        from tools.lib.subcategory_contract import load_contract, passes_gate
        contract = load_contract(contract_path)
        filtered: list[AggregatedProduct] = []
        for agg in report.aggregated:
            ok, reason = passes_gate(agg.product_name, agg.brand, contract)
            if ok:
                filtered.append(agg)
            else:
                print(f"  REJECTED (subcategory): {agg.product_name} -- {reason}", file=sys.stderr)
        print(f"  Subcategory gate: {len(report.aggregated)} -> {len(filtered)} products", file=sys.stderr)
        report.aggregated = filtered

    report.shortlist, report.rejected = _build_shortlist(report.aggregated)

    multi = [a for a in report.aggregated if a.source_count >= 2]
    print(f"  Total unique products: {len(report.aggregated)}", file=sys.stderr)
    print(f"  Multi-source products: {len(multi)}", file=sys.stderr)
    print(f"  Shortlisted: {len(report.shortlist)}", file=sys.stderr)

    # --- Step 4: Validate DONE ---
    report.validation_errors = _validate_done(report)
    if report.validation_errors:
        print(f"\n[research] VALIDATION ISSUES:", file=sys.stderr)
        for err in report.validation_errors:
            print(f"  - {err}", file=sys.stderr)

    # --- Step 5: Write outputs ---
    report_path = base / "research_report.md"
    shortlist_path = base / "shortlist.json"

    _write_research_report(report, report_path)
    _write_shortlist_json(report, shortlist_path)

    print(f"\n[research] Wrote {report_path}", file=sys.stderr)
    print(f"[research] Wrote {shortlist_path}", file=sys.stderr)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Evidence-first research agent")
    parser.add_argument("--video-id", required=True, help="Video ID")
    parser.add_argument("--niche", required=True, help="Product niche")
    parser.add_argument("--output-dir", default="", help="Output directory (overrides video path)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--force", action="store_true", help="Force re-run")
    args = parser.parse_args()

    load_env_file()

    output_dir = Path(args.output_dir) if args.output_dir else None
    report = run_reviews_research(
        args.video_id, args.niche,
        output_dir=output_dir,
        dry_run=args.dry_run,
        force=args.force,
    )

    # Print summary
    print(f"\nResearch Summary: {args.niche}")
    print(f"  Sources reviewed: {len(report.sources_reviewed)}")
    print(f"  Products found: {len(report.aggregated)}")
    print(f"  Shortlisted: {len(report.shortlist)}")

    if report.shortlist:
        print(f"\n  Shortlist:")
        for i, agg in enumerate(report.shortlist, 1):
            sources = ", ".join(e.source_name for e in agg.evidence)
            label = f" [{agg.primary_label}]" if agg.primary_label else ""
            print(f"    {i:2d}. {agg.product_name:<50s}{label} ({sources})")

    if report.validation_errors:
        print(f"\n  VALIDATION ISSUES:")
        for err in report.validation_errors:
            print(f"    - {err}")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
