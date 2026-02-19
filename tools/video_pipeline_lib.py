"""
Shared library for the RayViewsLab video pipeline.

Extracted from top5_video_pipeline.py so that pipeline.py and
pipeline_step_*.py can import without pulling in the full CLI.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import math
import os
import random
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from lib.common import now_iso


# ---------------------------------------------------------------------------
# Section 1 — Data models & constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent))
DAILY_CATEGORIES_FILE = BASE_DIR / "config" / "daily_categories.json"
SUPABASE_ENV_FILE = Path(os.path.expanduser("~/.config/newproject/supabase.env"))


def atomic_write_json(path: Path, data, indent: int = 2) -> Path:
    """Write JSON atomically: tmp + fsync + os.replace."""
    tmp = path.with_suffix(".tmp")
    payload = json.dumps(data, indent=indent, ensure_ascii=False).encode("utf-8")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))
    return path


def supabase_env() -> Tuple[str, str]:
    """Return (url, key) from env vars or ~/.config/newproject/supabase.env fallback."""
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if url and key:
        return url, key
    if SUPABASE_ENV_FILE.exists():
        try:
            for raw in SUPABASE_ENV_FILE.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if k == "SUPABASE_URL" and not url:
                    url = v
                elif k == "SUPABASE_SERVICE_ROLE_KEY" and not key:
                    key = v
        except Exception:
            pass
    return url, key


@dataclass
class Product:
    product_title: str
    asin: str
    current_price_usd: float
    rating: float
    review_count: int
    feature_bullets: List[str]
    amazon_url: str
    affiliate_url: str
    available: bool = True
    ranking_score: float = 0.0


STOPWORDS = {
    "top",
    "best",
    "for",
    "and",
    "the",
    "a",
    "an",
    "with",
    "of",
    "on",
    "in",
    "to",
    "from",
    "new",
    "latest",
    "2024",
    "2025",
    "2026",
}

SEGMENT_TYPES = [
    "HOOK", "CREDIBILITY", "CRITERIA",
    "PRODUCT_INTRO", "PRODUCT_DEMO", "PRODUCT_REVIEW", "PRODUCT_RANK",
    "FORWARD_HOOK", "WINNER_REINFORCEMENT", "ENDING_DECISION",
    "COMPARISON", "TIER_BREAK", "SURPRISE_PICK", "MYTH_BUST", "WINNER_TEASE",
]

PRODUCT_SEGMENT_TYPES = {"PRODUCT_INTRO", "PRODUCT_DEMO", "PRODUCT_REVIEW", "PRODUCT_RANK"}


# ---------------------------------------------------------------------------
# Section 2 — Parsing & scraping utilities
# ---------------------------------------------------------------------------

def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def slugify(value: str, max_len: int = 56) -> str:
    out = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    out = re.sub(r"_+", "_", out)
    return (out[:max_len] or "theme").strip("_")


def now_date() -> str:
    return dt.date.today().isoformat()


def parse_float(text: str) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", text.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    cleaned = text.replace(",", "")
    m = re.search(r"\$?\s*(\d+(?:\.\d{1,2})?)", cleaned)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def parse_int(text: str) -> Optional[int]:
    if not text:
        return None
    cleaned = text.replace(",", "")
    m = re.search(r"(\d+)", cleaned)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def parse_review_count(text: str) -> Optional[int]:
    if not text:
        return None
    raw = text.strip().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*([kKmM]?)", raw)
    if not m:
        return None
    value = float(m.group(1))
    suffix = m.group(2).lower()
    if suffix == "k":
        value *= 1000
    elif suffix == "m":
        value *= 1_000_000
    try:
        return int(value)
    except ValueError:
        return None


def theme_tokens(theme: str) -> List[str]:
    raw = re.findall(r"[a-z0-9]+", (theme or "").lower())
    return [t for t in raw if t not in STOPWORDS and len(t) >= 3]


def theme_match_score(title: str, tokens: List[str]) -> float:
    if not title or not tokens:
        return 0.0
    low = title.lower()
    hits = sum(1 for t in tokens if t in low)
    return hits / max(len(tokens), 1)


def append_affiliate_tag(url: str, affiliate_tag: str) -> str:
    if not affiliate_tag:
        return url
    if "tag=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}tag={affiliate_tag}"


def fetch_html(url: str, timeout: int = 30) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
        method="GET",
    )
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def load_bs4():
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Missing dependency: beautifulsoup4. Install with: pip install beautifulsoup4"
        ) from exc
    return BeautifulSoup


def extract_asin_from_url(url: str) -> str:
    m = re.search(r"/dp/([A-Z0-9]{10})", url or "")
    if m:
        return m.group(1)
    m = re.search(r"/gp/product/([A-Z0-9]{10})", url or "")
    if m:
        return m.group(1)
    return ""


def canonical_amazon_url(href: str, asin: str) -> str:
    if asin:
        return f"https://www.amazon.com/dp/{asin}"
    if href.startswith("http"):
        return href
    return urljoin("https://www.amazon.com", href)


def product_score(rating: float, reviews: int, price: float) -> float:
    review_strength = math.log10(max(reviews, 1))
    price_midpoint_bonus = max(0.0, 1.0 - abs(price - 85.0) / 150.0)
    return (rating * 1.6) + (review_strength * 1.1) + (price_midpoint_bonus * 0.5)


def parse_search_results(
    html: str,
    min_rating: float,
    min_reviews: int,
    min_price: float,
    max_price: float,
) -> List[Dict]:
    BeautifulSoup = load_bs4()
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select('div.s-result-item[data-component-type="s-search-result"]')
    out: List[Dict] = []
    for card in cards:
        asin = (card.get("data-asin") or "").strip().upper()
        if len(asin) != 10:
            continue

        title_el = (
            card.select_one('[data-cy="title-recipe"] a')
            or card.select_one("h2 a")
            or card.select_one("a.s-line-clamp-4.s-link-style.a-text-normal")
            or card.select_one("a.a-link-normal.s-no-outline")
        )
        link_el = (
            card.select_one('[data-cy="title-recipe"] a')
            or card.select_one("h2 a")
            or card.select_one("a.a-link-normal.s-no-outline")
        )
        price_el = card.select_one("span.a-price span.a-offscreen")
        rating_el = card.select_one("span.a-icon-alt")
        reviews_el = (
            card.select_one("a.s-underline-link-text")
            or card.select_one("span.a-size-base.s-underline-text")
            or card.select_one('a[href*="#customerReviews"]')
        )

        title = normalize_ws(title_el.get_text(" ", strip=True) if title_el else "")
        href = link_el.get("href", "") if link_el else ""
        price_val = parse_price(price_el.get_text(" ", strip=True) if price_el else "")
        rating_val = parse_float(rating_el.get_text(" ", strip=True) if rating_el else "")
        reviews_val = parse_review_count(reviews_el.get_text(" ", strip=True) if reviews_el else "")

        if not title or not href:
            continue
        if price_val is None or rating_val is None or reviews_val is None:
            continue
        if rating_val < min_rating or reviews_val < min_reviews:
            continue
        if price_val < min_price or price_val > max_price:
            continue

        out.append(
            {
                "asin": asin,
                "title": title,
                "url": canonical_amazon_url(href, asin),
                "price": price_val,
                "rating": rating_val,
                "reviews": reviews_val,
            }
        )
    return out


def parse_feature_bullets(html: str) -> Tuple[List[str], bool]:
    BeautifulSoup = load_bs4()
    soup = BeautifulSoup(html, "html.parser")
    bullets: List[str] = []
    for li in soup.select("#feature-bullets li"):
        txt = normalize_ws(li.get_text(" ", strip=True))
        if txt and txt.lower() not in {"see more"}:
            bullets.append(txt)
    unavailable_text = normalize_ws(soup.get_text(" ", strip=True)).lower()
    unavailable = "currently unavailable" in unavailable_text
    return bullets[:6], not unavailable


def extract_image_candidates_from_product_html(html: str) -> List[str]:
    urls: List[str] = []

    def add(url: str):
        u = normalize_ws(url).replace("\\/", "/")
        if not u or not u.startswith("http"):
            return
        if ".m.media-amazon.com" not in u and "images-na.ssl-images-amazon.com" not in u:
            return
        if u not in urls:
            urls.append(u)

    for m in re.finditer(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    ):
        add(m.group(1))

    for key in ("hiRes", "large", "mainUrl"):
        for m in re.finditer(rf'"{key}"\s*:\s*"([^"]+)"', html):
            add(m.group(1))

    # fallback generic URL scan
    for m in re.finditer(r"https://[^\"'\s]+(?:jpg|jpeg|png|webp)", html, flags=re.IGNORECASE):
        add(m.group(0))

    return urls[:24]


def download_binary(url: str, path: Path, timeout: int = 40) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.amazon.com/",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if not data:
            return False
        path.write_bytes(data)
        return True
    except Exception:  # noqa: BLE001
        return False


def ensure_placeholder_frame(out_dir: Path) -> Path:
    path = out_dir / "assets" / "fallback_frame.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path

    try:
        cmd = [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x20232a:s=1920x1080",
            "-frames:v",
            "1",
            "-y",
            str(path),
        ]
        p = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if p.returncode == 0 and path.exists():
            return path
    except Exception:  # noqa: BLE001
        pass

    one_px = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wn+3nQAAAAASUVORK5CYII="
    )
    path.write_bytes(one_px)
    return path


def download_amazon_reference_images(products: List[Product], out_dir: Path) -> Tuple[Path, Dict[str, Dict]]:
    ref_dir = out_dir / "assets" / "ref"
    ref_dir.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Dict] = {}

    for p in products:
        asin = p.asin.upper().strip()
        hero_path = ref_dir / f"{asin}_hero.jpg"
        life_path = ref_dir / f"{asin}_life.jpg"
        hero_src = ""
        life_src = ""
        errors: List[str] = []

        try:
            html = fetch_html(p.amazon_url)
            candidates = extract_image_candidates_from_product_html(html)
            if not candidates:
                errors.append("no_image_candidates_found")
            hero_src = candidates[0] if candidates else ""
            life_src = candidates[1] if len(candidates) > 1 else hero_src
            if hero_src and not download_binary(hero_src, hero_path):
                errors.append("hero_download_failed")
            if life_src and not download_binary(life_src, life_path):
                errors.append("life_download_failed")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"product_page_fetch_failed: {exc}")

        manifest[asin] = {
            "asin": asin,
            "amazon_url": p.amazon_url,
            "hero_ref_path": str(hero_path),
            "life_ref_path": str(life_path),
            "hero_source_url": hero_src,
            "life_source_url": life_src,
            "hero_exists": hero_path.exists(),
            "life_exists": life_path.exists(),
            "errors": errors,
        }

    manifest_path = out_dir / "amazon_reference_manifest.json"
    atomic_write_json(manifest_path, manifest)
    return manifest_path, manifest


def load_daily_categories() -> List[Dict]:
    try:
        raw = DAILY_CATEGORIES_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return []

    cats = data.get("categories", [])
    return cats if isinstance(cats, list) else []


def resolve_amazon_search_url_for_category(category: str) -> str:
    if not category:
        return ""

    want_label = category.strip().lower()
    want_slug = slugify(category, 120)

    for cat in load_daily_categories():
        if not isinstance(cat, dict):
            continue
        slug = str(cat.get("slug", "")).strip().lower()
        label = str(cat.get("label", "")).strip().lower()
        amazon = cat.get("amazon") or {}
        if not isinstance(amazon, dict):
            continue
        search_url = str(amazon.get("searchUrl") or "").strip()
        if not search_url:
            continue
        if want_slug and slug == want_slug:
            return search_url
        if want_label and label == want_label:
            return search_url

    return ""


def amazon_search_url_with_page(base_url: str, *, theme_fallback: str, page: int) -> str:
    if not base_url:
        q = quote_plus(theme_fallback)
        base_url = f"https://www.amazon.com/s?k={q}"

    parsed = urlparse(base_url)
    q = [(k, v) for (k, v) in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() != "page"]

    if not any(k == "k" for (k, _) in q):
        q.append(("k", theme_fallback))

    q.append(("page", str(page)))
    return urlunparse(parsed._replace(query=urlencode(q, doseq=True)))


def parse_run_date_from_dirname(name: str) -> Optional[dt.date]:
    m = re.search(r"(\d{4}-\d{2}-\d{2})$", name or "")
    if not m:
        return None
    try:
        return dt.date.fromisoformat(m.group(1))
    except ValueError:
        return None


def collect_recent_asins(output_root: Path, days: int) -> set[str]:
    if days <= 0 or not output_root.exists():
        return set()
    today = dt.date.today()
    cutoff = today - dt.timedelta(days=days)
    seen: set[str] = set()

    for run_dir in output_root.iterdir():
        if not run_dir.is_dir():
            continue
        run_date = parse_run_date_from_dirname(run_dir.name)
        if not run_date or run_date < cutoff:
            continue
        products_json = run_dir / "product_selection.json"
        if not products_json.exists():
            continue
        try:
            data = json.loads(products_json.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, list):
            continue
        for row in data:
            asin = str((row or {}).get("asin", "")).strip().upper()
            if len(asin) == 10:
                seen.add(asin)
    return seen


def discover_products_scrape(
    theme: str,
    affiliate_tag: str,
    top_n: int,
    min_rating: float,
    min_reviews: int,
    min_price: float,
    max_price: float,
    max_pages: int,
    excluded_asins: set[str],
    min_theme_match: float,
    search_url: str = "",
) -> List[Product]:
    candidate_map: Dict[str, Dict] = {}
    tokens = theme_tokens(theme)

    for page in range(1, max_pages + 1):
        url = amazon_search_url_with_page(search_url, theme_fallback=theme, page=page)
        html = fetch_html(url)
        parsed = parse_search_results(
            html=html,
            min_rating=min_rating,
            min_reviews=min_reviews,
            min_price=min_price,
            max_price=max_price,
        )
        for item in parsed:
            asin = item["asin"]
            if asin in excluded_asins:
                continue
            if theme_match_score(item["title"], tokens) < min_theme_match:
                continue
            existing = candidate_map.get(asin)
            if not existing or item["reviews"] > existing["reviews"]:
                candidate_map[asin] = item
        if len(candidate_map) >= (top_n * 4):
            break
        time.sleep(0.8 + random.random() * 0.7)

    if not candidate_map:
        raise RuntimeError(
            "No products discovered from Amazon search with current filters."
        )

    enriched: List[Product] = []
    for _, item in sorted(candidate_map.items(), key=lambda kv: kv[1]["reviews"], reverse=True):
        try:
            product_html = fetch_html(item["url"])
            bullets, available = parse_feature_bullets(product_html)
        except Exception:  # noqa: BLE001
            bullets, available = [], True
        if not available:
            continue

        asin = item["asin"]
        score = product_score(item["rating"], item["reviews"], item["price"])
        enriched.append(
            Product(
                product_title=item["title"],
                asin=asin,
                current_price_usd=float(item["price"]),
                rating=float(item["rating"]),
                review_count=int(item["reviews"]),
                feature_bullets=bullets,
                amazon_url=item["url"],
                affiliate_url=append_affiliate_tag(item["url"], affiliate_tag),
                available=available,
                ranking_score=score,
            )
        )
        if len(enriched) >= top_n:
            break

    if len(enriched) < top_n:
        raise RuntimeError(
            f"Only {len(enriched)} products matched. Try lowering filters or using another theme."
        )

    return sorted(enriched, key=lambda p: p.ranking_score, reverse=True)[:top_n]


# ---------------------------------------------------------------------------
# Section 3 — Script generation & extraction
# ---------------------------------------------------------------------------

def _build_structure_instructions(variation_plan: Optional[Dict]) -> List[str]:
    """Build the REQUIRED STRUCTURE prompt lines from variation_plan or defaults."""
    if variation_plan:
        pi = variation_plan.get("prompt_instructions", {})
        sel = variation_plan.get("selections", {})
        lines = [
            "REQUIRED STRUCTURE:",
            f"Structure template: {sel.get('structure_template', 'classic_countdown')}",
            f"Description: {pi.get('structure_description', '')}",
            f"Flow: {pi.get('structure_flow', '')}",
            "",
            f"Editorial format: {pi.get('editorial_format', 'classic_top5')} ({pi.get('editorial_format_label', '')})",
            f"Editorial description: {pi.get('editorial_format_description', '')}",
        ]
        fmt_rules = pi.get("editorial_format_rules", [])
        if isinstance(fmt_rules, list):
            for r in fmt_rules[:6]:
                lines.append(f"Editorial rule: {r}")
        chapter_pattern = pi.get("editorial_chapter_pattern", "")
        if chapter_pattern:
            lines.append(f"Chapter pattern: {chapter_pattern}")
        lines.extend(
            [
            "",
            f"Product block pattern: {sel.get('product_block_pattern', 'classic_4seg')}",
            f"Segments per product: {', '.join(pi.get('segments_per_product', ['PRODUCT_INTRO', 'PRODUCT_DEMO', 'PRODUCT_REVIEW', 'PRODUCT_RANK']))}",
            f"Product order: {pi.get('product_order', 'ascending_rank')}",
            "",
            f"Opener style: {sel.get('opener_style', 'overwhelm')}",
            f"Opener guidance: {pi.get('opener_description', '')}",
            ]
        )
        opener_tpl = pi.get("opener_template", "")
        if opener_tpl:
            lines.append(f"Opener template example: {opener_tpl}")
        lines.extend([
            "",
            f"Visual style: {pi.get('visual_description', '')}",
            f"Voice pacing: {pi.get('voice_description', '')} (target {pi.get('voice_wpm_target', 150)} wpm)",
            "",
            f"CTA line: {pi.get('cta_line', '')}",
            f"Disclosure: {pi.get('disclosure_text', '')}",
        ])

        angle_prompt = pi.get("marketing_angle_prompt", "")
        angle_desc = pi.get("marketing_angle", "")
        if angle_prompt:
            lines.extend([
                "",
                "MARKETING ANGLE (this frames the ENTIRE video perspective):",
                f"Angle: {angle_desc}",
                angle_prompt,
            ])

        offer_ctx = pi.get("offer_context", "")
        avatar_ctx = pi.get("customer_avatar", "")
        fallback = pi.get("category_context_fallback", "")
        if offer_ctx or avatar_ctx:
            lines.append("")
            lines.append("CATEGORY CONTEXT (use this to write with deep brand knowledge):")
            if offer_ctx:
                lines.append(f"Offer landscape: {offer_ctx[:1500]}")
            if avatar_ctx:
                lines.append(f"Customer avatar: {avatar_ctx[:1500]}")
        elif fallback:
            lines.extend(["", f"CATEGORY CONTEXT NOTE: {fallback}"])

        return lines

    return [
        "REQUIRED STRUCTURE:",
        "1x HOOK (cold open, 30-50 words, curiosity loop, never greet audience)",
        "1x CREDIBILITY (process proof, 30-40 words)",
        "1x CRITERIA (3 ranking criteria, 40-60 words)",
        "Per product (5 products, #5 to #1):",
        "  1x PRODUCT_INTRO (problem + presentation + award title)",
        "  1x PRODUCT_DEMO (specs/data with visual_hint of product in use)",
        "  1x PRODUCT_REVIEW (good + surprise + honest limitation)",
        "  1x PRODUCT_RANK (who should buy + who should NOT buy + short punch <=4 words)",
        "  1x FORWARD_HOOK (tease next product, except after #1)",
        "1x WINNER_REINFORCEMENT (recap by awards + buyer mapping + 'If you only buy one...')",
        "1x ENDING_DECISION (CTA + affiliate disclosure + AI disclosure)",
    ]


def build_structured_script_prompt(
    products: List[Product],
    theme: str,
    channel_name: str,
    variation_plan: Optional[Dict] = None,
) -> str:
    """Build a prompt that instructs the LLM to return a structured JSON script."""
    ranked = sorted(products, key=lambda p: p.ranking_score, reverse=True)
    show_order = list(reversed(ranked))  # #5 -> #1

    products_json = []
    for idx, p in enumerate(show_order):
        rank = 5 - idx
        products_json.append({
            "rank": rank,
            "name": p.product_title,
            "category": theme,
            "key_features": p.feature_bullets[:5],
            "price_range": f"${p.current_price_usd:.2f}",
            "rating": f"{p.rating:.1f}",
            "review_count": p.review_count,
            "amazon_affiliate_url": p.affiliate_url,
        })

    prompt_lines = [
        "You are a structured script generator inside an automated production pipeline.",
        "",
        "You are NOT writing a YouTube script for humans to read.",
        "You are generating machine-usable structured narration data.",
        "",
        "The output feeds multiple systems:",
        "- Dzine image generation (scene visualization via visual_hint)",
        "- ElevenLabs voice synthesis (spoken narration)",
        "- DaVinci Resolve timeline assembly (segments -> tracks)",
        "- YouTube upload metadata (description + chapters)",
        "",
        f"Channel: {channel_name}",
        "Goal: help viewers decide what to buy.",
        "",
        "INPUT PRODUCTS:",
        json.dumps(products_json, indent=2),
        "",
        "VIDEO TARGET: 8-12 minutes, 1100-1800 spoken words.",
        "",
        "REQUIRED SEGMENT TYPES (enum):",
        ", ".join(SEGMENT_TYPES),
        "",
        *_build_structure_instructions(variation_plan),
        "",
        "STYLE RULES:",
        "- Spoken language: clear, natural, conversational",
        "- Not technical, not corporate, not exaggerated influencer tone",
        "- Contractions mandatory (it's, don't, you'll)",
        "- At least 1 sentence <=4 words per product ('Worth it.', 'Not even close.')",
        "- At least 1 cross-product comparison",
        "- For each product, include at least 1 evidence-backed statement (comparison, measured trade-off, or review/rating context)",
        "- For each product, include at least 1 contraindication ('who should NOT buy')",
        "- Varied product openers (question, statement, contrast, data, confession)",
        "- Top 2 products: more emotional emphasis, slightly longer narration",
        "- Winner must contain explicit buying recommendation",
        "- Never: 'welcome back', 'hey guys', 'in today's video', sponsor language",
        "",
        "NARRATION RULES (optimized for voice synthesis):",
        "- Short sentences (avoid complex punctuation)",
        "- No emojis, no markdown, no parentheses",
        "- Reference product name naturally but don't repeat excessively",
        "",
        "VISUAL_HINT RULES (for Dzine image generation):",
        "- Describe product IN USE, not static appearance",
        "- Be specific and realistic",
        "- BAD: 'A mouse on a desk'",
        "- GOOD: 'A clean minimal desk setup where the user quickly switches devices using the wireless mouse'",
        "- Required for: HOOK, CREDIBILITY, CRITERIA, PRODUCT_INTRO, PRODUCT_DEMO, WINNER_REINFORCEMENT",
        "",
        "ANTI-AI RULES (hard enforcement):",
        "- Never use: 'let's dive in', 'game-changer', 'without further ado', 'sleek design',",
        "  'packed with features', 'bang for your buck', 'at the end of the day',",
        "  'takes it to the next level', 'boasts', 'elevate your experience'",
        "- No 3+ adjectives in a row",
        "- No press release or e-commerce language",
        "",
        "JSON SANITY RULES (hard enforcement):",
        "- Output must be strictly valid JSON (RFC 8259).",
        "- Never include raw tab characters or control characters in strings.",
        "- Never include literal newlines inside JSON strings. For line breaks, use the two-character sequence \\n.",
        "",
        "OUTPUT FORMAT (strict JSON, nothing else):",
        """{
  "video_title": "string (SEO-optimized, under 70 chars)",
  "estimated_duration_minutes": number,
  "total_word_count": number,
  "segments": [
    {
      "type": "SEGMENT_TYPE",
      "narration": "spoken text",
      "visual_hint": "scene description for image generation",
      "product_name": "only for PRODUCT_* types",
      "role": "optional; use 'evidence' for proof-heavy segments"
    }
  ],
  "youtube": {
    "description": "full YouTube description with affiliate links and disclosures",
    "tags": ["tag1", "tag2"],
    "chapters": [
      {"time": "0:00", "label": "chapter name"}
    ]
  }
}""",
        "",
        "Return ONLY valid JSON. No explanations outside JSON.",
    ]
    return "\n".join(prompt_lines)


def parse_structured_script(raw_text: str) -> Dict:
    """Parse and validate structured JSON script output from the LLM."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Structured script is not valid JSON: {e}")

    for key in ("video_title", "segments", "youtube"):
        if key not in data:
            raise RuntimeError(f"Structured script missing required key: {key}")

    segments = data.get("segments", [])
    if not isinstance(segments, list) or len(segments) < 10:
        raise RuntimeError(f"Expected at least 10 segments, got {len(segments) if isinstance(segments, list) else 0}")

    for i, seg in enumerate(segments):
        seg_type = seg.get("type", "")
        if seg_type not in SEGMENT_TYPES:
            raise RuntimeError(f"Segment {i}: invalid type '{seg_type}'. Must be one of {SEGMENT_TYPES}")
        if not seg.get("narration"):
            raise RuntimeError(f"Segment {i} ({seg_type}): missing narration")
        if seg_type in PRODUCT_SEGMENT_TYPES and not seg.get("product_name"):
            raise RuntimeError(f"Segment {i} ({seg_type}): missing product_name")

    total_words = sum(len(seg.get("narration", "").split()) for seg in segments)
    data["total_word_count"] = total_words

    return data


def extract_dzine_scenes(structured_script: Dict) -> List[Dict]:
    """Extract visual_hint scenes from structured script for Dzine image generation."""
    scenes = []
    for seg in structured_script.get("segments", []):
        hint = seg.get("visual_hint", "").strip()
        if hint:
            scenes.append({
                "product_name": seg.get("product_name", ""),
                "visual_hint": hint,
                "segment_type": seg["type"],
            })
    return scenes


def extract_voice_segments(structured_script: Dict) -> List[Dict]:
    """Extract narration segments for ElevenLabs voice synthesis."""
    voice_segs = []
    for i, seg in enumerate(structured_script.get("segments", [])):
        narration = seg.get("narration", "").strip()
        if narration:
            voice_segs.append({
                "segment_id": f"seg_{i:02d}_{seg['type'].lower()}",
                "type": seg["type"],
                "narration": narration,
                "product_name": seg.get("product_name", ""),
                "word_count": len(narration.split()),
            })
    return voice_segs


def extract_davinci_segments(structured_script: Dict) -> List[Dict]:
    """Extract typed segments for DaVinci Resolve timeline assembly."""
    timeline = []
    for i, seg in enumerate(structured_script.get("segments", [])):
        narration = seg.get("narration", "")
        words = len(narration.split())
        est_seconds = round(words / 150 * 60, 1)
        timeline.append({
            "segment_id": f"seg_{i:02d}",
            "type": seg["type"],
            "product_name": seg.get("product_name", ""),
            "word_count": words,
            "estimated_seconds": est_seconds,
            "has_visual": bool(seg.get("visual_hint")),
        })
    return timeline


def write_structured_script(structured_script: Dict, out_dir: Path) -> Path:
    """Write the structured script JSON to the run directory."""
    path = out_dir / "script.json"
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(structured_script, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


def load_products_json(path: Path) -> List[Product]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    out: List[Product] = []
    for row in rows:
        try:
            price = float(row["current_price_usd"])
        except (ValueError, TypeError):
            price = 0.0
        try:
            rating = float(row["rating"])
        except (ValueError, TypeError):
            rating = 0.0
        try:
            review_count = int(row["review_count"])
        except (ValueError, TypeError):
            review_count = 0
        try:
            ranking_score = float(row.get("ranking_score", 0.0))
        except (ValueError, TypeError):
            ranking_score = 0.0
        out.append(
            Product(
                product_title=row["product_title"],
                asin=row["asin"],
                current_price_usd=price,
                rating=rating,
                review_count=review_count,
                feature_bullets=list(row.get("feature_bullets") or []),
                amazon_url=row["amazon_url"],
                affiliate_url=row["affiliate_url"],
                available=bool(row.get("available", True)),
                ranking_score=ranking_score,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Data models & constants
    "Product",
    "SEGMENT_TYPES",
    "PRODUCT_SEGMENT_TYPES",
    "STOPWORDS",
    "BASE_DIR",
    "DAILY_CATEGORIES_FILE",
    "SUPABASE_ENV_FILE",
    "supabase_env",
    "atomic_write_json",
    # Parsing & scraping utilities
    "normalize_ws",
    "slugify",
    "now_date",
    "now_iso",
    "parse_float",
    "parse_price",
    "parse_int",
    "parse_review_count",
    "theme_tokens",
    "theme_match_score",
    "append_affiliate_tag",
    "fetch_html",
    "load_bs4",
    "extract_asin_from_url",
    "canonical_amazon_url",
    "product_score",
    "parse_search_results",
    "parse_feature_bullets",
    "extract_image_candidates_from_product_html",
    "download_binary",
    "ensure_placeholder_frame",
    "download_amazon_reference_images",
    "load_daily_categories",
    "resolve_amazon_search_url_for_category",
    "amazon_search_url_with_page",
    "parse_run_date_from_dirname",
    "collect_recent_asins",
    "discover_products_scrape",
    # Script generation & extraction
    "build_structured_script_prompt",
    "parse_structured_script",
    "extract_dzine_scenes",
    "extract_voice_segments",
    "extract_davinci_segments",
    "write_structured_script",
    "load_products_json",
]
