#!/usr/bin/env python3
"""Amazon US product verification — PA-API or browser fallback.

For each shortlisted product, verifies it exists on Amazon US,
extracts ASIN, price, and generates an affiliate link.

Usage:
    python3 tools/amazon_verify.py --shortlist shortlist.json --video-id xyz
    python3 tools/amazon_verify.py --shortlist shortlist.json --output verified.json

Stdlib only (+ Playwright for browser fallback).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.common import load_env_file, now_iso, project_root, require_env

VIDEOS_BASE = project_root() / "artifacts" / "videos"


class _AmazonBlockError(Exception):
    """Amazon CAPTCHA or bot-detection block."""
    pass


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class VerifiedProduct:
    """A product verified to exist on Amazon US."""
    product_name: str
    brand: str = ""
    asin: str = ""
    amazon_url: str = ""
    affiliate_url: str = ""
    affiliate_short_url: str = ""  # amzn.to link from SiteStripe
    amazon_title: str = ""
    amazon_price: str = ""
    amazon_rating: str = ""
    amazon_reviews: str = ""
    amazon_image_url: str = ""
    match_confidence: str = "low"  # low, medium, high
    verification_method: str = ""  # "paapi" or "browser"
    evidence: list[dict] = field(default_factory=list)
    key_claims: list[str] = field(default_factory=list)
    error: str = ""


# ---------------------------------------------------------------------------
# Affiliate link generation
# ---------------------------------------------------------------------------


def _make_affiliate_url(asin: str, tag: str) -> str:
    """Generate an Amazon affiliate URL."""
    return f"https://www.amazon.com/dp/{asin}?tag={tag}"


def _normalize_search_query(brand: str, product_name: str) -> str:
    """Build a clean Amazon search query from brand + product name.

    Strips parentheticals, non-word characters, and collapses whitespace.
    Result: clean "Brand Model" only.
    """
    # Start from product_name (may already include brand)
    name = product_name
    # Strip trailing parenthetical content: "(2024 Edition)" etc.
    name = re.sub(r'\s*\([^)]*\)\s*$', '', name)
    # Remove non-word characters except embedded hyphens and spaces
    name = re.sub(r'[^\w\s-]', '', name)
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    # If brand not already in name, prepend it
    if brand and not name.lower().startswith(brand.lower()):
        brand_clean = re.sub(r'[^\w\s-]', '', brand).strip()
        name = f"{brand_clean} {name}"
    return name.strip()


# ---------------------------------------------------------------------------
# SiteStripe selectors (best-effort, updatable)
# ---------------------------------------------------------------------------

SITESTRIPE_SELECTORS = {
    "bar": ["#amzn-ss-wrap", "#site-stripe", "[id*='sitestripe' i]", "[id*='SiteStripe']"],
    "get_link": ["#amzn-ss-text-link", "text=Text", "text=Get Link"],
    "short_link": ["text=Short Link", "text=Short", "#amzn-ss-text-shortlink-widget"],
    "link_output": [
        "input[value*='amzn.to']",
        "#amzn-ss-text-shortlink-textarea",
        "input[readonly]",
    ],
}


def _find_first_visible(context, selectors: list[str], timeout: int = 2000):
    """Try selectors in order, return first visible locator or None."""
    for sel in selectors:
        try:
            loc = context.locator(sel).first
            if loc.is_visible(timeout=timeout):
                return loc
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# PA-API v5 (optional)
# ---------------------------------------------------------------------------


def _paapi_available() -> bool:
    """Check if PA-API credentials are configured."""
    return bool(
        os.environ.get("AMAZON_PAAPI_ACCESS_KEY", "").strip()
        and os.environ.get("AMAZON_PAAPI_SECRET_KEY", "").strip()
    )


def _paapi_search(keyword: str, tag: str) -> list[dict]:
    """Search Amazon via PA-API v5 SearchItems.

    Returns list of {asin, title, price, image_url, url}.
    Requires AMAZON_PAAPI_ACCESS_KEY, AMAZON_PAAPI_SECRET_KEY env vars.
    """
    access_key = os.environ["AMAZON_PAAPI_ACCESS_KEY"].strip()
    secret_key = os.environ["AMAZON_PAAPI_SECRET_KEY"].strip()

    host = "webservices.amazon.com"
    path = "/paapi5/searchitems"
    region = "us-east-1"
    service = "ProductAdvertisingAPI"
    target = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems"

    payload = json.dumps({
        "Keywords": keyword,
        "PartnerTag": tag,
        "PartnerType": "Associates",
        "Marketplace": "www.amazon.com",
        "Resources": [
            "ItemInfo.Title",
            "Offers.Listings.Price",
            "Images.Primary.Large",
        ],
        "SearchIndex": "All",
        "ItemCount": 5,
    })

    # AWS Signature V4
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    # Canonical request
    canonical_headers = (
        f"content-encoding:amz-1.0\n"
        f"content-type:application/json; charset=UTF-8\n"
        f"host:{host}\n"
        f"x-amz-date:{amz_date}\n"
        f"x-amz-target:{target}\n"
    )
    signed_headers = "content-encoding;content-type;host;x-amz-date;x-amz-target"
    payload_hash = hashlib.sha256(payload.encode()).hexdigest()
    canonical = f"POST\n{path}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

    # String to sign
    scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n"
        + hashlib.sha256(canonical.encode()).hexdigest()
    )

    # Signing key
    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k_date = _sign(f"AWS4{secret_key}".encode(), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

    auth_header = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    req = urllib.request.Request(
        f"https://{host}{path}",
        method="POST",
        data=payload.encode(),
        headers={
            "Content-Type": "application/json; charset=UTF-8",
            "Content-Encoding": "amz-1.0",
            "Host": host,
            "X-Amz-Date": amz_date,
            "X-Amz-Target": target,
            "Authorization": auth_header,
        },
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    results = []
    for item in data.get("SearchResult", {}).get("Items", []):
        asin = item.get("ASIN", "")
        title = item.get("ItemInfo", {}).get("Title", {}).get("DisplayValue", "")
        price = ""
        listings = item.get("Offers", {}).get("Listings", [])
        if listings:
            price_obj = listings[0].get("Price", {})
            price = price_obj.get("DisplayAmount", "")
        image_url = item.get("Images", {}).get("Primary", {}).get("Large", {}).get("URL", "")

        results.append({
            "asin": asin,
            "title": title,
            "price": price,
            "image_url": image_url,
            "url": f"https://www.amazon.com/dp/{asin}",
        })

    return results


# ---------------------------------------------------------------------------
# Browser fallback
# ---------------------------------------------------------------------------


def _browser_verify_product(
    product_name: str, tag: str
) -> VerifiedProduct | None:
    """Legacy wrapper — delegates to PDP flow."""
    return _browser_verify_product_pdp(product_name, "", tag)


def _browser_verify_product_pdp(
    product_name: str,
    brand: str,
    tag: str,
    *,
    video_id: str = "",
    product_index: int = 0,
) -> VerifiedProduct | None:
    """Search Amazon, open PDP, extract details, capture SiteStripe link.

    Uses the running Brave browser via CDP.
    """
    from tools.lib.brave_profile import connect_or_launch

    browser, context, should_close, pw = connect_or_launch(headless=False)
    page = context.new_page()

    # Resolve screenshot directory
    screen_dir = None
    if video_id:
        from tools.lib.video_paths import VideoPaths
        screen_dir = VideoPaths(video_id).amazon_screens
        screen_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Build clean query
        query = _normalize_search_query(brand, product_name)
        search_url = f"https://www.amazon.com/s?k={urllib.parse.quote_plus(query)}"
        page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
        # Wait for search results to render (not just DOM load)
        try:
            page.wait_for_selector(
                '[data-component-type="s-search-result"]', timeout=10000,
            )
        except Exception:
            page.wait_for_timeout(3000)  # fallback static wait

        # Check for captcha / bot detection
        captcha_form = page.locator('form[action*="validateCaptcha"]').count() > 0
        robot_text = False
        try:
            robot_text = page.locator("text=Sorry, we just need to make sure you're not a robot").count() > 0
        except Exception:
            pass
        if captcha_form or robot_text:
            try:
                from tools.lib.notify import notify_action_required
                notify_action_required(
                    video_id or "unknown", "verify",
                    "Amazon CAPTCHA detected",
                    next_action="Solve CAPTCHA in Brave browser, then re-run verify",
                )
            except Exception:
                pass
            raise _AmazonBlockError("Amazon CAPTCHA / bot-detection block")

        # Get up to 5 search result cards
        cards = page.locator('[data-component-type="s-search-result"]')
        count = min(cards.count(), 5)

        # Build (index, card_title, similarity, asin) list sorted by similarity
        card_info: list[tuple[int, str, float, str]] = []
        for i in range(count):
            card = cards.nth(i)
            try:
                card_asin = card.get_attribute("data-asin", timeout=2000) or ""
                if not card_asin:
                    continue
                title = ""
                try:
                    # Amazon 2025+ layout: brand in h2, product in .a-text-normal
                    brand_text = ""
                    try:
                        brand_text = card.locator("h2").first.inner_text(timeout=2000).strip()
                    except Exception:
                        pass
                    model_text = ""
                    try:
                        model_text = card.locator(
                            ".a-size-medium.a-color-base.a-text-normal, "
                            ".a-size-base-plus.a-color-base.a-text-normal"
                        ).first.inner_text(timeout=2000).strip()
                    except Exception:
                        pass
                    if brand_text and model_text:
                        title = f"{brand_text} {model_text}"
                    elif model_text:
                        title = model_text
                    elif brand_text:
                        title = brand_text
                except Exception:
                    pass
                sim = _title_similarity(product_name, title)
                if sim >= 0.5:
                    card_info.append((i, title, sim, card_asin))
            except Exception:
                continue

        card_info.sort(key=lambda x: -x[2])

        if count == 0:
            print(f"    No search result cards found for: {query}", file=sys.stderr)
            return None

        if not card_info:
            # Dump first card title for debugging
            debug_title = ""
            if count > 0:
                try:
                    t_el = cards.nth(0).locator("h2 a span, h2 span").first
                    debug_title = t_el.inner_text(timeout=2000).strip()[:80]
                except Exception:
                    debug_title = "(could not read)"
            print(
                f"    {count} cards but none matched (sim < 0.5) for: {query}"
                f"  [card0: {debug_title!r}]",
                file=sys.stderr,
            )
            return None

        for card_idx, card_title, card_sim, card_asin in card_info:

            try:
                # Navigate directly to PDP via ASIN (avoids click-target issues)
                asin = card_asin
                pdp_url = f"https://www.amazon.com/dp/{asin}"
                page.goto(pdp_url, wait_until="domcontentloaded", timeout=15000)

                # Wait for PDP to load
                try:
                    page.wait_for_selector("#productTitle", timeout=10000)
                except Exception:
                    print(f"    PDP did not load #productTitle for ASIN {asin}", file=sys.stderr)
                    page.go_back(wait_until="domcontentloaded", timeout=10000)
                    page.wait_for_timeout(1000)
                    continue

                # Extract title from PDP
                pdp_title = ""
                try:
                    pdp_title = page.locator("#productTitle").first.inner_text(timeout=3000).strip()
                except Exception:
                    pass

                # Check similarity against PDP title
                pdp_sim = _title_similarity(product_name, pdp_title)
                if pdp_sim < 0.70:
                    print(f"    PDP title mismatch ({pdp_sim:.2f} < 0.70): {pdp_title[:60]}", file=sys.stderr)
                    page.go_back(wait_until="domcontentloaded", timeout=10000)
                    page.wait_for_timeout(1000)
                    continue

                # Extract price from PDP
                price = ""
                try:
                    offscreen = page.locator(".a-price .a-offscreen").first
                    price = offscreen.inner_text(timeout=2000).strip()
                except Exception:
                    pass

                # Extract rating
                rating = ""
                try:
                    alt_el = page.locator("#acrPopover .a-icon-alt").first
                    r_text = alt_el.inner_text(timeout=2000)
                    m = re.search(r"(\d+\.?\d*)\s*out\s*of", r_text)
                    if m:
                        rating = m.group(1)
                except Exception:
                    pass

                # Extract reviews count
                reviews = ""
                try:
                    rev_el = page.locator("#acrCustomerReviewText").first
                    rev_text = rev_el.inner_text(timeout=2000)
                    rm = re.search(r'([\d,]+)', rev_text)
                    if rm:
                        reviews = rm.group(1).replace(",", "")
                except Exception:
                    pass

                # Extract image
                image_url = ""
                try:
                    img = page.locator("#landingImage, #imgBlkFront").first
                    image_url = img.get_attribute("src", timeout=2000) or ""
                except Exception:
                    pass

                # Take PDP screenshot
                if screen_dir:
                    try:
                        page.screenshot(path=str(screen_dir / f"{product_index:02d}_{asin}_pdp.png"))
                    except Exception:
                        pass

                # --- SiteStripe capture ---
                short_url = ""
                ss_error = ""

                # Try main page first, then iframes
                contexts_to_try = [page]
                try:
                    for frame in page.frames:
                        if frame != page.main_frame:
                            contexts_to_try.append(frame)
                except Exception:
                    pass

                for ss_ctx in contexts_to_try:
                    bar = _find_first_visible(ss_ctx, SITESTRIPE_SELECTORS["bar"], timeout=2000)
                    if not bar:
                        continue

                    # Click "Get Link" / "Text"
                    get_link = _find_first_visible(ss_ctx, SITESTRIPE_SELECTORS["get_link"], timeout=2000)
                    if get_link:
                        try:
                            get_link.click(timeout=3000)
                            page.wait_for_timeout(1000)
                        except Exception:
                            continue

                    # Click "Short Link"
                    short_btn = _find_first_visible(ss_ctx, SITESTRIPE_SELECTORS["short_link"], timeout=2000)
                    if short_btn:
                        try:
                            short_btn.click(timeout=3000)
                            page.wait_for_timeout(1500)
                        except Exception:
                            pass

                    # Extract the short URL
                    link_out = _find_first_visible(ss_ctx, SITESTRIPE_SELECTORS["link_output"], timeout=3000)
                    if link_out:
                        try:
                            val = link_out.get_attribute("value", timeout=2000) or ""
                            if not val:
                                val = link_out.inner_text(timeout=2000)
                            if "amzn.to" in val:
                                short_url = val.strip()
                        except Exception:
                            pass

                    if short_url:
                        # Take SiteStripe screenshot
                        if screen_dir:
                            try:
                                page.screenshot(path=str(screen_dir / f"{product_index:02d}_{asin}_sitestripe.png"))
                            except Exception:
                                pass
                        break

                if not short_url:
                    ss_error = "ACTION_REQUIRED: SiteStripe not visible -- log in to Amazon Associates"

                confidence = "high" if pdp_sim >= 0.90 else ("medium" if pdp_sim >= 0.75 else "low")

                return VerifiedProduct(
                    product_name=product_name,
                    brand=brand,
                    asin=asin,
                    amazon_url=f"https://www.amazon.com/dp/{asin}",
                    affiliate_url=_make_affiliate_url(asin, tag) if tag else f"https://www.amazon.com/dp/{asin}",
                    affiliate_short_url=short_url,
                    amazon_title=pdp_title,
                    amazon_price=price,
                    amazon_rating=rating,
                    amazon_reviews=reviews,
                    amazon_image_url=image_url,
                    match_confidence=confidence,
                    verification_method="browser",
                    error=ss_error,
                )

            except Exception as exc:
                print(f"    PDP exception for ASIN {card_asin}: {exc}", file=sys.stderr)
                # Try to go back to search results for next card
                try:
                    page.go_back(wait_until="domcontentloaded", timeout=10000)
                    page.wait_for_timeout(1000)
                except Exception:
                    pass
                continue

        return None

    except Exception as exc:
        print(f"    Browser verification failed: {exc}", file=sys.stderr)
        return None
    finally:
        page.close()
        if should_close:
            context.close()
        pw.stop()


def _title_similarity(query: str, title: str) -> float:
    """Simple word-overlap similarity score between query and Amazon title."""
    if not query or not title:
        return 0.0
    q_words = set(re.findall(r'\w+', query.lower()))
    t_words = set(re.findall(r'\w+', title.lower()))
    # Remove very common words
    stopwords = {"the", "a", "an", "and", "or", "for", "with", "in", "of", "to", "is", "by", "on", "at", "it", "new"}
    q_words -= stopwords
    t_words -= stopwords
    if not q_words:
        return 0.0
    overlap = q_words & t_words
    return len(overlap) / len(q_words)


# ---------------------------------------------------------------------------
# Verification orchestrator
# ---------------------------------------------------------------------------


def verify_products(
    shortlist: list[dict],
    *,
    associate_tag: str = "",
    video_id: str = "",
) -> list[VerifiedProduct]:
    """Verify each shortlisted product exists on Amazon US.

    Uses PA-API if configured, otherwise browser fallback with PDP navigation.
    """
    load_env_file()
    tag = associate_tag or os.environ.get("AMAZON_ASSOCIATE_TAG", "").strip()
    if not tag:
        print("[verify] Warning: AMAZON_ASSOCIATE_TAG not set, affiliate links will be plain URLs",
              file=sys.stderr)

    use_paapi = _paapi_available()
    method = "PA-API" if use_paapi else "Browser (PDP)"
    print(f"[verify] Method: {method}", file=sys.stderr)
    print(f"[verify] Products to verify: {len(shortlist)}", file=sys.stderr)

    verified: list[VerifiedProduct] = []
    consecutive_failures = 0

    for i, item in enumerate(shortlist):
        product_name = item.get("product_name", "")
        brand = item.get("brand", "")
        clean_query = _normalize_search_query(brand, product_name)
        print(f"\n  [{i+1}/{len(shortlist)}] {product_name}...", file=sys.stderr)
        print(f"    Query: {clean_query}", file=sys.stderr)

        if use_paapi:
            # PA-API search
            try:
                results = _paapi_search(clean_query, tag)
                if results:
                    best = results[0]
                    score = _title_similarity(product_name, best["title"])
                    confidence = "high" if score > 0.6 else ("medium" if score > 0.35 else "low")
                    vp = VerifiedProduct(
                        product_name=product_name,
                        brand=brand,
                        asin=best["asin"],
                        amazon_url=best["url"],
                        affiliate_url=_make_affiliate_url(best["asin"], tag) if tag else best["url"],
                        amazon_title=best["title"],
                        amazon_price=best["price"],
                        amazon_image_url=best.get("image_url", ""),
                        match_confidence=confidence,
                        verification_method="paapi",
                        evidence=item.get("sources", []),
                        key_claims=item.get("key_claims", []),
                    )
                    verified.append(vp)
                    consecutive_failures = 0
                    print(f"    OK: {vp.asin} ({confidence}) -- {vp.amazon_title[:60]}", file=sys.stderr)
                else:
                    consecutive_failures += 1
                    print(f"    NOT FOUND on Amazon", file=sys.stderr)
            except Exception as exc:
                consecutive_failures += 1
                print(f"    PA-API error: {exc}", file=sys.stderr)
        else:
            # Browser PDP flow with retry
            from tools.lib.retry import with_retry

            vp = None
            try:
                vp = with_retry(
                    lambda pn=product_name, br=brand, t=tag, vid=video_id, idx=i:
                        _browser_verify_product_pdp(pn, br, t, video_id=vid, product_index=idx),
                    max_retries=1,
                    base_delay_s=5.0,
                )
            except _AmazonBlockError:
                consecutive_failures += 1
                print(f"    BLOCKED: Amazon CAPTCHA/bot detection", file=sys.stderr)
            except Exception as exc:
                consecutive_failures += 1
                print(f"    Browser error: {exc}", file=sys.stderr)

            if vp:
                vp.evidence = item.get("sources", [])
                vp.key_claims = item.get("key_claims", [])
                verified.append(vp)
                consecutive_failures = 0
                short_info = f" | short={vp.affiliate_short_url[:30]}" if vp.affiliate_short_url else ""
                print(f"    OK: {vp.asin} ({vp.match_confidence}) -- {vp.amazon_title[:60]}{short_info}", file=sys.stderr)
                if vp.error:
                    print(f"    Note: {vp.error}", file=sys.stderr)
            elif vp is None and consecutive_failures == 0:
                print(f"    NO MATCH: {product_name}", file=sys.stderr)
            else:
                print(f"    NOT FOUND / verification failed", file=sys.stderr)

            # Consecutive failure pause: if 3+ in a row, likely rate-limited
            if consecutive_failures >= 3:
                try:
                    from tools.lib.notify import notify_rate_limited
                    notify_rate_limited(video_id or "unknown", "verify", wait_minutes=1)
                except Exception:
                    pass
                print(f"    3+ consecutive failures — pausing 30s", file=sys.stderr)
                time.sleep(30)
                consecutive_failures = 0

            # Delay between browser searches to avoid throttling
            if i < len(shortlist) - 1:
                time.sleep(2.5)

    return verified


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write_verified(verified: list[VerifiedProduct], output_path: Path) -> None:
    """Write verified products to JSON."""
    data = {
        "verified_at": now_iso(),
        "count": len(verified),
        "products": [
            {
                "product_name": v.product_name,
                "brand": v.brand,
                "asin": v.asin,
                "amazon_url": v.amazon_url,
                "affiliate_url": v.affiliate_url,
                "affiliate_short_url": v.affiliate_short_url,
                "amazon_title": v.amazon_title,
                "amazon_price": v.amazon_price,
                "amazon_rating": v.amazon_rating,
                "amazon_reviews": v.amazon_reviews,
                "amazon_image_url": v.amazon_image_url,
                "match_confidence": v.match_confidence,
                "verification_method": v.verification_method,
                "evidence": v.evidence,
                "key_claims": v.key_claims,
                "error": v.error,
            }
            for v in verified
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_shortlist(path: Path) -> list[dict]:
    """Load shortlist JSON (as produced by reviews_research.py)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("shortlist", data if isinstance(data, list) else [])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Amazon US product verification")
    parser.add_argument("--shortlist", required=True, help="Path to shortlist JSON")
    parser.add_argument("--video-id", default="", help="Video ID")
    parser.add_argument("--output", default="", help="Output path for verified JSON")
    args = parser.parse_args()

    load_env_file()

    shortlist = load_shortlist(Path(args.shortlist))
    if not shortlist:
        print("Empty shortlist", file=sys.stderr)
        return 1

    verified = verify_products(shortlist, video_id=args.video_id)

    print(f"\nVerified: {len(verified)}/{len(shortlist)} products found on Amazon US")

    # Write output
    if args.video_id:
        output_path = VIDEOS_BASE / args.video_id / "inputs" / "verified.json"
    elif args.output:
        output_path = Path(args.output)
    else:
        output_path = project_root() / "data" / "verified.json"

    write_verified(verified, output_path)
    print(f"Wrote {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
