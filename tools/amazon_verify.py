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
    """Search Amazon in the browser and verify a product exists.

    Uses the running Brave browser via CDP.
    """
    from tools.lib.brave_profile import connect_or_launch

    browser, context, should_close, pw = connect_or_launch(headless=False)
    page = context.new_page()

    try:
        # Search Amazon for the product
        query = urllib.parse.quote_plus(product_name)
        search_url = f"https://www.amazon.com/s?k={query}"
        page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(3000)

        # Check for captcha
        if page.locator('form[action*="validateCaptcha"]').count() > 0:
            print(f"    CAPTCHA detected — skipping browser verification",
                  file=sys.stderr)
            return None

        # Get first few search result cards
        cards = page.locator('[data-component-type="s-search-result"]')
        count = min(cards.count(), 5)

        best_match: VerifiedProduct | None = None
        best_score = 0.0

        for i in range(count):
            card = cards.nth(i)
            try:
                asin = card.get_attribute("data-asin", timeout=2000) or ""
                if not asin:
                    continue

                # Title
                title = ""
                try:
                    title_el = card.locator("h2 a span, h2 span").first
                    title = title_el.inner_text(timeout=2000).strip()
                except Exception:
                    pass

                # Price — prefer .a-offscreen for clean formatting
                price = ""
                try:
                    offscreen = card.locator(".a-price .a-offscreen").first
                    price = offscreen.inner_text(timeout=1500).strip()
                except Exception:
                    try:
                        pw_ = card.locator(".a-price .a-price-whole").first
                        pf = card.locator(".a-price .a-price-fraction").first
                        whole = pw_.inner_text(timeout=1500).replace("\n", "").strip().rstrip(".")
                        frac = pf.inner_text(timeout=1500).replace("\n", "").strip()
                        price = f"${whole}.{frac}"
                    except Exception:
                        pass

                # Rating — try multiple selector patterns
                rating = ""
                try:
                    for r_sel in [".a-icon-star-small .a-icon-alt", ".a-icon-alt"]:
                        r_el = card.locator(r_sel).first
                        if r_el.count() > 0:
                            r_text = r_el.inner_text(timeout=1500)
                            m = re.search(r"(\d+\.?\d*)\s*out\s*of", r_text)
                            if m:
                                rating = m.group(1)
                                break
                except Exception:
                    pass

                # Reviews count — look for (18.9K) or (1,234) patterns
                reviews = ""
                try:
                    # Find the link near ratings that contains the count
                    rev_links = card.locator("a")
                    for ri in range(min(rev_links.count(), 15)):
                        rt = rev_links.nth(ri).inner_text(timeout=800).strip()
                        # Match patterns like (18.9K) or (1,234)
                        rm = re.search(r"\(?([\d,\.]+[KkMm]?)\)?", rt)
                        if rm and rt.startswith("("):
                            raw = rm.group(1).replace(",", "")
                            # Expand K/M suffixes
                            if raw.upper().endswith("K"):
                                reviews = str(int(float(raw[:-1]) * 1000))
                            elif raw.upper().endswith("M"):
                                reviews = str(int(float(raw[:-1]) * 1000000))
                            else:
                                reviews = raw
                            break
                except Exception:
                    pass

                # Image
                image_url = ""
                try:
                    img = card.locator(".s-image").first
                    image_url = img.get_attribute("src", timeout=1500) or ""
                except Exception:
                    pass

                # Score the match
                score = _title_similarity(product_name, title)

                if score > best_score:
                    best_score = score
                    confidence = "high" if score > 0.6 else ("medium" if score > 0.35 else "low")
                    best_match = VerifiedProduct(
                        product_name=product_name,
                        asin=asin,
                        amazon_url=f"https://www.amazon.com/dp/{asin}",
                        affiliate_url=_make_affiliate_url(asin, tag),
                        amazon_title=title,
                        amazon_price=price,
                        amazon_rating=rating,
                        amazon_reviews=reviews,
                        amazon_image_url=image_url,
                        match_confidence=confidence,
                        verification_method="browser",
                    )

            except Exception as exc:
                continue

        return best_match

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
) -> list[VerifiedProduct]:
    """Verify each shortlisted product exists on Amazon US.

    Uses PA-API if configured, otherwise browser fallback.
    """
    load_env_file()
    tag = associate_tag or os.environ.get("AMAZON_ASSOCIATE_TAG", "").strip()
    if not tag:
        print("[verify] Warning: AMAZON_ASSOCIATE_TAG not set, affiliate links will be plain URLs",
              file=sys.stderr)

    use_paapi = _paapi_available()
    method = "PA-API" if use_paapi else "Browser"
    print(f"[verify] Method: {method}", file=sys.stderr)
    print(f"[verify] Products to verify: {len(shortlist)}", file=sys.stderr)

    verified: list[VerifiedProduct] = []

    for i, item in enumerate(shortlist):
        product_name = item.get("product_name", "")
        brand = item.get("brand", "")
        print(f"\n  [{i+1}/{len(shortlist)}] {product_name}...", file=sys.stderr)

        if use_paapi:
            # PA-API search
            try:
                results = _paapi_search(f"{brand} {product_name}", tag)
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
                    print(f"    OK: {vp.asin} ({confidence}) — {vp.amazon_title[:60]}", file=sys.stderr)
                else:
                    print(f"    NOT FOUND on Amazon", file=sys.stderr)
            except Exception as exc:
                print(f"    PA-API error: {exc}", file=sys.stderr)
        else:
            # Browser fallback
            vp = _browser_verify_product(product_name, tag)
            if vp:
                vp.brand = brand
                vp.evidence = item.get("sources", [])
                vp.key_claims = item.get("key_claims", [])
                verified.append(vp)
                print(f"    OK: {vp.asin} ({vp.match_confidence}) — {vp.amazon_title[:60]}", file=sys.stderr)
            else:
                print(f"    NOT FOUND / verification failed", file=sys.stderr)

            # Small delay between browser searches to avoid throttling
            if i < len(shortlist) - 1:
                time.sleep(1.5)

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
                "amazon_title": v.amazon_title,
                "amazon_price": v.amazon_price,
                "amazon_rating": v.amazon_rating,
                "amazon_reviews": v.amazon_reviews,
                "amazon_image_url": v.amazon_image_url,
                "match_confidence": v.match_confidence,
                "verification_method": v.verification_method,
                "evidence": v.evidence,
                "key_claims": v.key_claims,
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

    verified = verify_products(shortlist)

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
