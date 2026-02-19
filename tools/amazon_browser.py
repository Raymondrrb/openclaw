"""Browser-based Amazon product discovery via OpenClaw's Brave CDP connection.

Drives Amazon search through a logged-in Brave browser to avoid 403/CAPTCHA
blocks that hit raw urllib.request. Returns AmazonProduct objects compatible
with the rest of the pipeline.

Uses the same CDP connection pattern as tools/lib/dzine_browser.py.
Stdlib + Playwright only.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

# Ensure repo root is on sys.path (for standalone CLI usage)
_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.amazon_research import (
    AmazonProduct,
    clean_amazon_url,
    extract_asin,
    make_tag_url,
)
from tools.lib.brave_profile import connect_or_launch, is_browser_running

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# CSS selectors for Amazon search results (JS-evaluated in-page)
# These mirror the DOM structure of Amazon's search results grid.
SEARCH_RESULT_JS = """() => {
    const results = [];
    const items = document.querySelectorAll('div[data-asin][data-component-type="s-search-result"]');
    for (const item of items) {
        const asin = item.getAttribute('data-asin');
        if (!asin) continue;

        // Title
        const titleEl = item.querySelector('h2 a span, h2 span');
        const title = titleEl ? titleEl.innerText.trim() : '';
        if (!title) continue;

        // URL
        const linkEl = item.querySelector('h2 a');
        const href = linkEl ? linkEl.href : '';

        // Price
        const priceWhole = item.querySelector('.a-price-whole');
        const priceFrac = item.querySelector('.a-price-fraction');
        let price = '';
        if (priceWhole) {
            price = '$' + priceWhole.innerText.replace(/[^0-9]/g, '');
            if (priceFrac) price += '.' + priceFrac.innerText.replace(/[^0-9]/g, '');
        }

        // Rating
        const ratingEl = item.querySelector('.a-icon-alt');
        const ratingText = ratingEl ? ratingEl.innerText : '';
        const ratingMatch = ratingText.match(/([\\.0-9]+)\\s*out/);
        const rating = ratingMatch ? ratingMatch[1] : '';

        // Reviews count
        const reviewsEl = item.querySelector('a[href*="#customerReviews"] span, span[data-component-type="s-client-side-analytics"] .a-size-base');
        let reviews = '';
        if (reviewsEl) {
            const raw = reviewsEl.innerText.replace(/[^0-9,]/g, '');
            if (raw) reviews = raw;
        }

        // Image
        const imgEl = item.querySelector('.s-image');
        const imageUrl = imgEl ? imgEl.src : '';

        // Sponsored check
        const sponsoredEl = item.querySelector('.puis-label-popover-default, .s-label-popover-default');
        const isSponsored = !!sponsoredEl;

        results.push({
            asin, title, href, price, rating, reviews, imageUrl, isSponsored,
        });
    }
    return results;
}"""

# Product detail page extraction JS
PRODUCT_DETAIL_JS = """() => {
    const result = {};

    // Feature bullets
    const bullets = [];
    const bulletEls = document.querySelectorAll('#feature-bullets li span.a-list-item');
    for (const el of bulletEls) {
        const text = el.innerText.trim();
        if (text && text.length > 5) bullets.push(text);
    }
    result.benefits = bullets.slice(0, 5);

    // Availability
    const availEl = document.querySelector('#availability span');
    result.availability = availEl ? availEl.innerText.trim() : '';

    // Rating from detail page
    const ratingEl = document.querySelector('#acrPopover .a-icon-alt');
    result.rating = ratingEl ? ratingEl.innerText.match(/([\\d.]+)/)?.[1] || '' : '';

    // Review count from detail page
    const reviewEl = document.querySelector('#acrCustomerReviewText');
    result.reviews = reviewEl ? reviewEl.innerText.replace(/[^0-9,]/g, '') : '';

    // Main image
    const mainImg = document.querySelector('#landingImage, #imgBlkFront');
    result.imageUrl = mainImg ? (mainImg.getAttribute('data-old-hires') || mainImg.src) : '';

    // Price
    const priceEl = document.querySelector('.a-price .a-offscreen');
    result.price = priceEl ? priceEl.innerText.trim() : '';

    // Title
    const titleEl = document.querySelector('#productTitle');
    result.title = titleEl ? titleEl.innerText.trim() : '';

    return result;
}"""

NAVIGATION_SLEEP_S = 1.5  # human-like pacing between pages
MAX_SEARCH_PAGES = 3
DEFAULT_TOP_N = 5


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------


class AmazonBrowserError(RuntimeError):
    """Raised when browser-based Amazon interaction fails."""


# ---------------------------------------------------------------------------
# Session management (mirrors dzine_browser.py pattern)
# ---------------------------------------------------------------------------

_session_pw = None
_session_browser = None
_session_context = None
_session_page = None
_session_should_close = False


def _get_or_create_page():
    """Get a reusable page for Amazon browsing.

    Returns (page, is_new_page) tuple.
    """
    global _session_pw, _session_browser, _session_context, _session_page, _session_should_close

    if _session_page is not None:
        try:
            _session_page.evaluate("() => true")
            return _session_page, False
        except Exception:
            _session_page = None
            _session_browser = None
            _session_context = None
            if _session_pw:
                try:
                    _session_pw.stop()
                except Exception:
                    pass
            _session_pw = None

    if not is_browser_running():
        raise AmazonBrowserError(
            "OpenClaw browser not running. Start with: openclaw browser start"
        )

    browser, context, should_close, pw = connect_or_launch(headless=False)
    page = context.new_page()

    _session_pw = pw
    _session_browser = browser
    _session_context = context
    _session_page = page
    _session_should_close = should_close

    return page, True


def close_session() -> None:
    """Explicitly close the shared session."""
    global _session_pw, _session_browser, _session_context, _session_page, _session_should_close
    if _session_page:
        import threading

        def _cleanup():
            try:
                _session_page.close()
            except Exception:
                pass
            if _session_should_close:
                try:
                    _session_context.close()
                except Exception:
                    pass
            try:
                _session_pw.stop()
            except Exception:
                pass

        t = threading.Thread(target=_cleanup, daemon=True)
        t.start()
        t.join(timeout=5)

    _session_pw = None
    _session_browser = None
    _session_context = None
    _session_page = None
    _session_should_close = False


# ---------------------------------------------------------------------------
# Amazon navigation
# ---------------------------------------------------------------------------


def _ensure_amazon_page(page) -> None:
    """Navigate to Amazon if not already there."""
    current = page.url or ""
    if "amazon.com" not in current:
        page.goto("https://www.amazon.com/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)


def _check_logged_in(page) -> bool:
    """Check if user is logged into Amazon (not 'Hello, sign in')."""
    try:
        return page.evaluate("""() => {
            const el = document.querySelector('#nav-link-accountList span.nav-line-1');
            if (!el) return false;
            const text = (el.innerText || '').trim().toLowerCase();
            return !text.includes('sign in') && !text.includes('hello, sign');
        }""")
    except Exception:
        return False


def _check_captcha(page) -> bool:
    """Check if Amazon is showing a CAPTCHA page."""
    try:
        return page.evaluate("""() => {
            const body = document.body.innerText || '';
            return body.includes('Type the characters you see')
                || body.includes('Enter the characters you see')
                || !!document.querySelector('form[action*="validateCaptcha"]');
        }""")
    except Exception:
        return False


def search_products(page, query: str, page_num: int = 1) -> list[dict]:
    """Navigate to Amazon search and extract product cards.

    Returns list of raw product dicts from JS extraction.
    """
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.amazon.com/s?k={encoded}"
    if page_num > 1:
        url += f"&page={page_num}"

    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)  # let search results load

    if _check_captcha(page):
        raise AmazonBrowserError(
            "Amazon CAPTCHA detected. Solve it manually in the browser, then retry."
        )

    # Wait for result items to appear
    try:
        page.wait_for_selector(
            'div[data-component-type="s-search-result"]',
            timeout=10000,
        )
    except Exception:
        print(f"[amazon] No search results found for: {query} (page {page_num})",
              file=sys.stderr)
        return []

    results = page.evaluate(SEARCH_RESULT_JS)
    return results or []


def enrich_product(page, url: str) -> dict:
    """Navigate to a product detail page and extract enrichment data.

    Returns dict with benefits, availability, rating, reviews, imageUrl, price, title.
    """
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    if _check_captcha(page):
        raise AmazonBrowserError(
            "Amazon CAPTCHA detected on product page. Solve manually, then retry."
        )

    try:
        detail = page.evaluate(PRODUCT_DETAIL_JS)
    except Exception as exc:
        print(f"[amazon] Could not extract product detail: {exc}", file=sys.stderr)
        detail = {}

    return detail


# ---------------------------------------------------------------------------
# Scoring / filtering
# ---------------------------------------------------------------------------


def _parse_reviews_count(raw: str) -> int:
    """Parse review count string like '1,234' → 1234."""
    cleaned = re.sub(r"[^0-9]", "", raw)
    return int(cleaned) if cleaned else 0


def _parse_price(raw: str) -> float:
    """Parse price string like '$29.99' → 29.99."""
    cleaned = re.sub(r"[^0-9.]", "", raw)
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _parse_rating(raw: str) -> float:
    """Parse rating string like '4.5' → 4.5."""
    try:
        return float(raw)
    except (ValueError, TypeError):
        return 0.0


def _ranking_score(item: dict) -> float:
    """Compute a ranking score for sorting candidates.

    Factors: rating, review count, non-sponsored.
    """
    rating = _parse_rating(item.get("rating", ""))
    reviews = _parse_reviews_count(item.get("reviews", ""))
    is_sponsored = item.get("isSponsored", False)

    # Weighted score: rating matters, reviews validate, sponsored penalized
    score = rating * 10.0
    if reviews >= 100:
        score += 5.0
    if reviews >= 500:
        score += 5.0
    if reviews >= 1000:
        score += 5.0
    if reviews >= 5000:
        score += 5.0
    if is_sponsored:
        score -= 10.0

    return score


# ---------------------------------------------------------------------------
# Main discovery flow
# ---------------------------------------------------------------------------


def discover_products_browser(
    keyword: str,
    *,
    affiliate_tag: str = "",
    top_n: int = DEFAULT_TOP_N,
    min_rating: float = 3.5,
    min_reviews: int = 50,
    min_price: float = 0.0,
    max_price: float = 0.0,
    enrich: bool = True,
    max_pages: int = MAX_SEARCH_PAGES,
) -> list[AmazonProduct]:
    """Full browser-based Amazon product discovery.

    1. Search Amazon for keyword across multiple pages
    2. Filter by rating, reviews, price
    3. Enrich top candidates with product detail pages
    4. Return ranked AmazonProduct list

    Raises AmazonBrowserError if browser is unavailable or CAPTCHA blocks.
    """
    if not keyword:
        raise AmazonBrowserError("No search keyword provided")

    page, is_new = _get_or_create_page()
    _ensure_amazon_page(page)

    # Collect candidates from search pages
    all_candidates: list[dict] = []

    for page_num in range(1, max_pages + 1):
        print(f"[amazon] Searching page {page_num}: {keyword}", file=sys.stderr)
        results = search_products(page, keyword, page_num)
        print(f"[amazon] Found {len(results)} items on page {page_num}", file=sys.stderr)

        for item in results:
            # Skip items without ASIN or title
            if not item.get("asin") or not item.get("title"):
                continue

            # Filter by rating
            rating = _parse_rating(item.get("rating", ""))
            if rating > 0 and rating < min_rating:
                continue

            # Filter by review count
            reviews = _parse_reviews_count(item.get("reviews", ""))
            if reviews > 0 and reviews < min_reviews:
                continue

            # Filter by price
            price = _parse_price(item.get("price", ""))
            if min_price > 0 and price > 0 and price < min_price:
                continue
            if max_price > 0 and price > 0 and price > max_price:
                continue

            all_candidates.append(item)

        if page_num < max_pages:
            time.sleep(NAVIGATION_SLEEP_S)

    if not all_candidates:
        print(f"[amazon] No candidates found for: {keyword}", file=sys.stderr)
        return []

    # Deduplicate by ASIN
    seen_asins: set[str] = set()
    unique: list[dict] = []
    for item in all_candidates:
        asin = item["asin"]
        if asin not in seen_asins:
            seen_asins.add(asin)
            unique.append(item)

    # Sort by ranking score, take top_n * 2 for enrichment
    unique.sort(key=_ranking_score, reverse=True)
    candidates_to_enrich = unique[:top_n * 2]

    print(f"[amazon] {len(unique)} unique candidates, enriching top {len(candidates_to_enrich)}",
          file=sys.stderr)

    # Enrich top candidates
    enriched: list[dict] = []
    for item in candidates_to_enrich:
        if enrich:
            asin = item["asin"]
            product_url = f"https://www.amazon.com/dp/{asin}"
            try:
                detail = enrich_product(page, product_url)
                # Merge enrichment data (detail overrides search data where present)
                if detail.get("benefits"):
                    item["benefits"] = detail["benefits"]
                if detail.get("rating") and not item.get("rating"):
                    item["rating"] = detail["rating"]
                if detail.get("reviews") and not item.get("reviews"):
                    item["reviews"] = detail["reviews"]
                if detail.get("imageUrl"):
                    item["imageUrl"] = detail["imageUrl"]
                if detail.get("price") and not item.get("price"):
                    item["price"] = detail["price"]
            except AmazonBrowserError:
                raise  # CAPTCHA — abort
            except Exception as exc:
                print(f"[amazon] Enrichment failed for {asin}: {exc}", file=sys.stderr)

            time.sleep(NAVIGATION_SLEEP_S)

        enriched.append(item)

    # Re-sort after enrichment and take top_n
    enriched.sort(key=_ranking_score, reverse=True)
    final = enriched[:top_n]

    # Build AmazonProduct objects
    products: list[AmazonProduct] = []
    for rank, item in enumerate(final, 1):
        asin = item["asin"]
        amazon_url = clean_amazon_url(f"https://www.amazon.com/dp/{asin}")

        affiliate_url = ""
        if affiliate_tag:
            affiliate_url = make_tag_url(amazon_url, affiliate_tag)

        products.append(AmazonProduct(
            rank=rank,
            name=item.get("title", ""),
            price=item.get("price", ""),
            rating=item.get("rating", ""),
            reviews_count=item.get("reviews", ""),
            amazon_url=amazon_url,
            affiliate_url=affiliate_url,
            image_url=item.get("imageUrl", ""),
            benefits=item.get("benefits", []),
            asin=asin,
        ))

    return products


# ---------------------------------------------------------------------------
# CLI entry point (standalone testing)
# ---------------------------------------------------------------------------


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Amazon browser-based product discovery")
    parser.add_argument("--keyword", required=True, help="Search keyword / niche")
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N, help="Number of products")
    parser.add_argument("--tag", default="", help="Affiliate tag")
    parser.add_argument("--min-rating", type=float, default=3.5)
    parser.add_argument("--min-reviews", type=int, default=50)
    parser.add_argument("--min-price", type=float, default=0.0)
    parser.add_argument("--max-price", type=float, default=0.0)
    parser.add_argument("--no-enrich", action="store_true", help="Skip product detail enrichment")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    try:
        products = discover_products_browser(
            keyword=args.keyword,
            affiliate_tag=args.tag,
            top_n=args.top_n,
            min_rating=args.min_rating,
            min_reviews=args.min_reviews,
            min_price=args.min_price,
            max_price=args.max_price,
            enrich=not args.no_enrich,
        )
    except AmazonBrowserError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        close_session()

    if args.json:
        import dataclasses
        data = [dataclasses.asdict(p) for p in products]
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        for p in products:
            print(f"\n#{p.rank}: {p.name}")
            print(f"  ASIN: {p.asin}")
            print(f"  Price: {p.price}")
            print(f"  Rating: {p.rating} ({p.reviews_count} reviews)")
            print(f"  URL: {p.amazon_url}")
            if p.benefits:
                print(f"  Benefits: {len(p.benefits)} bullets")
                for b in p.benefits[:3]:
                    print(f"    - {b[:80]}")

    print(f"\n[amazon] Found {len(products)} products", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
