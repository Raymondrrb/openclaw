#!/usr/bin/env python3
"""Deep Amazon product intelligence collector via OpenClaw Browser.

Key behavior:
- Reads product page facts directly from the rendered Amazon page
- Scrolls to customer review sections and extracts buyer feedback snippets
- Selects multiple strong reference images per product (hero + alternatives)
- Produces token-efficient compact output for narrated script generation
- Writes learning-loop artifacts to Obsidian-compatible markdown + JSONL

No Firecrawl dependency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

NEGATIVE_MARKERS = {
    "issue",
    "problem",
    "bug",
    "failed",
    "return",
    "returned",
    "refund",
    "slow",
    "fragile",
    "flicker",
    "lag",
    "overheat",
    "inconsistent",
    "not",
    "however",
    "but",
    "wish",
    "noise",
    "disconnect",
    "drain",
}

THEME_KEYWORDS = {
    "display_quality": ["display", "screen", "resolution", "color", "brightness", "contrast", "panel"],
    "build_quality": ["build", "sturdy", "durable", "plastic", "metal", "stand", "hinge"],
    "setup_connectivity": ["setup", "install", "usb", "usb-c", "hdmi", "driver", "compatibility", "plug"],
    "value_price": ["price", "value", "money", "expensive", "cheap", "worth"],
    "performance": ["performance", "speed", "refresh", "latency", "response", "smooth"],
    "portability": ["portable", "lightweight", "travel", "weight", "battery"],
    "audio_quality": ["sound", "audio", "bass", "mic", "noise cancel", "anc"],
    "battery": ["battery", "charge", "charging", "runtime", "hours"],
}

SAFE_IMAGE_HOST_KEYWORDS = (
    "images-amazon.com",
    "media-amazon.com",
    "ssl-images-amazon",
    "amazonusercontent.com",
)

BROWSER_PROFILE = ""
DEBUG_BROWSER = os.getenv("AMAZON_INTEL_DEBUG", "").strip() not in {"", "0", "false", "False"}


@dataclass
class ProductSeed:
    rank: int
    asin: str
    title: str
    product_url: str


class BrowserError(RuntimeError):
    pass


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _slug(value: str, fallback: str = "item") -> str:
    raw = re.sub(r"[^a-zA-Z0-9_-]+", "-", (value or "").strip()).strip("-")
    return raw[:80] if raw else fallback


def _sha1_text(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _parse_asin(url: str) -> str:
    m = re.search(r"/dp/([A-Z0-9]{10})(?:[/?]|$)", url or "", flags=re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.search(r"/gp/product/([A-Z0-9]{10})(?:[/?]|$)", url or "", flags=re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return ""


def _parse_products_json(path: Path) -> list[ProductSeed]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("products") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError("products_json must contain an object with key 'products' as an array")

    seeds: list[ProductSeed] = []
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        product_url = str(row.get("product_url") or row.get("url") or "").strip()
        if not product_url:
            continue
        asin = str(row.get("asin") or _parse_asin(product_url)).strip().upper()
        title = str(row.get("title") or f"product-{i}").strip()
        rank = int(row.get("rank") or i)
        seeds.append(ProductSeed(rank=rank, asin=asin or f"UNKNOWN{i:02d}", title=title, product_url=product_url))

    if not seeds:
        raise ValueError("products_json did not provide any valid product_url rows")
    return seeds


def _parse_product_urls(urls: list[str]) -> list[ProductSeed]:
    seeds: list[ProductSeed] = []
    for i, url in enumerate(urls, start=1):
        clean = str(url or "").strip()
        if not clean:
            continue
        asin = _parse_asin(clean) or f"UNKNOWN{i:02d}"
        seeds.append(ProductSeed(rank=i, asin=asin, title=f"product-{i}", product_url=clean))
    return seeds


def _run_browser_json(args: list[str], timeout_ms: int = 45000, attempts: int = 3) -> dict[str, Any]:
    if attempts < 1:
        attempts = 1
    backoff = [0.8, 2.0, 5.0]
    last_error = "browser_unknown_error"

    for attempt in range(1, attempts + 1):
        cmd = ["openclaw", "browser", "--json", "--timeout", str(int(timeout_ms))]
        if BROWSER_PROFILE:
            cmd.extend(["--browser-profile", BROWSER_PROFILE])
        cmd.extend(args)
        if DEBUG_BROWSER:
            print(f"[amazon_intel][browser][attempt={attempt}] {' '.join(cmd)}", file=sys.stderr, flush=True)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=max(20.0, float(timeout_ms) / 1000.0 + 20.0),
            )
        except subprocess.TimeoutExpired:
            proc = subprocess.CompletedProcess(args=cmd, returncode=124, stdout="", stderr="browser_command_timeout")
        if proc.returncode == 0:
            out = (proc.stdout or "").strip()
            if not out:
                return {}
            try:
                return json.loads(out)
            except json.JSONDecodeError as exc:
                raise BrowserError(f"browser_non_json_output:{exc}") from None

        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        msg = stderr or stdout or f"browser_command_failed:{' '.join(args)}"
        if DEBUG_BROWSER:
            print(
                f"[amazon_intel][browser][attempt={attempt}] rc={proc.returncode} err={msg[:500]}",
                file=sys.stderr,
                flush=True,
            )
        last_error = msg

        recoverable = (
            "connectOverCDP" in msg
            or "Timeout" in msg
            or "timeout" in msg
            or "ECONNREFUSED" in msg
            or "browser target closed" in msg.lower()
        )
        if recoverable and attempt < attempts:
            # Try to revive the browser process for transient CDP failures.
            subprocess.run(
                [
                    "openclaw",
                    "browser",
                    "--json",
                    "--timeout",
                    "60000",
                    "--browser-profile",
                    BROWSER_PROFILE,
                    "start",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            time.sleep(backoff[min(attempt - 1, len(backoff) - 1)])
            continue
        break

    raise BrowserError(last_error)


def _browser_prepare() -> None:
    try:
        _run_browser_json(["start"], timeout_ms=45000)
    except BrowserError as exc:
        msg = str(exc)
        if "Profile" in msg and "not found" in msg:
            # Do not auto-create random profiles; fallback to the main OpenClaw profile.
            global BROWSER_PROFILE
            BROWSER_PROFILE = "openclaw"
            _run_browser_json(["start"], timeout_ms=60000)
            return
        raise


def _browser_cleanup_amazon_tabs(max_close: int = 80) -> dict[str, Any]:
    tabs_payload = _run_browser_json(["tabs"], timeout_ms=40000)
    tabs = tabs_payload.get("tabs") if isinstance(tabs_payload, dict) else []
    if not isinstance(tabs, list):
        return {"closed": 0, "scanned": 0}

    to_close: list[str] = []
    for tab in tabs:
        if not isinstance(tab, dict):
            continue
        tid = str(tab.get("targetId") or "").strip()
        if not tid:
            continue
        url = str(tab.get("url") or "").lower()
        typ = str(tab.get("type") or "").lower()
        if "amazon.com" in url or "media-amazon.com" in url:
            if typ in {"page", "iframe"}:
                to_close.append(tid)

    closed = 0
    for tid in to_close[: max(0, int(max_close))]:
        try:
            _run_browser_json(["close", tid], timeout_ms=12000)
            closed += 1
        except Exception:
            continue
    return {"closed": closed, "scanned": len(tabs)}


def _browser_open_product(url: str, timeout_ms: int = 60000) -> str:
    out = _run_browser_json(["open", url], timeout_ms=timeout_ms)
    tid = str(out.get("targetId") or "").strip()
    if not tid:
        raise BrowserError("browser_open_missing_target_id")
    _run_browser_json(["focus", tid], timeout_ms=15000)
    _run_browser_json(["wait", "--target-id", tid, "--load", "domcontentloaded", "--timeout-ms", "30000"], timeout_ms=40000)
    _run_browser_json(
        [
            "wait",
            "--target-id",
            tid,
            "--fn",
            "() => !!document.querySelector('#productTitle, #centerCol, body')",
            "--timeout-ms",
            "45000",
        ],
        timeout_ms=50000,
    )
    return tid


def _browser_close_tab(target_id: str) -> None:
    if not target_id:
        return
    try:
        _run_browser_json(["close", target_id], timeout_ms=12000)
    except Exception:
        pass


def _browser_wait(ms: int, target_id: str = "") -> None:
    cmd = ["wait", "--time", str(int(ms))]
    if target_id:
        cmd.extend(["--target-id", target_id])
    _run_browser_json(cmd, timeout_ms=max(10000, ms + 8000))


def _browser_eval(fn_code: str, target_id: str, timeout_ms: int = 50000) -> dict[str, Any]:
    out = _run_browser_json(["evaluate", "--target-id", target_id, "--fn", fn_code], timeout_ms=timeout_ms)
    result = out.get("result")
    if isinstance(result, dict):
        return result
    return {"value": result}


def _browser_snapshot_ai(target_id: str, limit: int = 260) -> dict[str, Any]:
    out = _run_browser_json(
        ["snapshot", "--target-id", target_id, "--format", "ai", "--limit", str(max(40, int(limit)))],
        timeout_ms=50000,
    )
    if not isinstance(out, dict):
        return {}
    return out


def _browser_click_get_link_from_snapshot(target_id: str) -> dict[str, Any]:
    shot = _browser_snapshot_ai(target_id, limit=320)
    refs = shot.get("refs")
    if not isinstance(refs, dict):
        return {"clicked": False, "reason": "snapshot_refs_missing"}

    candidates: list[tuple[str, str, str]] = []
    for ref, meta in refs.items():
        if not isinstance(meta, dict):
            continue
        role = str(meta.get("role") or "").lower()
        name = str(meta.get("name") or "")
        name_l = name.lower()
        if not name:
            continue
        if role not in {"button", "link", "menuitem", "tab", "generic"}:
            continue
        if "get link" in name_l or (("link" in name_l) and ("site" in name_l or "stripe" in name_l)):
            candidates.append((str(ref), role, name))

    if not candidates:
        # Fallback: scan snapshot text for references near "Get Link".
        snap_text = str(shot.get("snapshot") or "")
        for m in re.finditer(r"(get\s+link).*?\[ref=([a-z]\d+)\]", snap_text, flags=re.IGNORECASE):
            candidates.append((m.group(2), "unknown", m.group(1)))

    if not candidates:
        return {"clicked": False, "reason": "get_link_ref_not_found"}

    for ref, role, name in candidates[:5]:
        try:
            _run_browser_json(["click", ref, "--target-id", target_id], timeout_ms=25000)
            _browser_wait(900, target_id=target_id)
            return {"clicked": True, "ref": ref, "role": role, "name": name}
        except Exception:
            continue
    return {"clicked": False, "reason": "click_failed"}


def _normalize_sitestripe_short_url(raw_url: str) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return ""
    if text.startswith("//"):
        text = "https:" + text
    if not re.match(r"^https?://", text, flags=re.IGNORECASE):
        if "amzn.to/" in text:
            text = "https://" + text.lstrip("/")
        else:
            return ""
    parsed = urllib.parse.urlsplit(text)
    host = (parsed.netloc or "").lower()
    if host not in {"amzn.to", "www.amzn.to"}:
        return ""
    path = (parsed.path or "").strip()
    if not path or path == "/":
        return ""
    return f"https://amzn.to{path}"


def _browser_extract_sitestripe_short_url(target_id: str, attempts: int = 3) -> dict[str, Any]:
    extract_fn = """() => {
      const clean = (v) => (v || '').toString().replace(/\\s+/g, ' ').trim();
      const pick = (items) => {
        for (const item of items) {
          const v = clean(item);
          if (/https?:\\/\\/(www\\.)?amzn\\.to\\//i.test(v)) return v;
          if (/^(www\\.)?amzn\\.to\\//i.test(v)) return 'https://' + v.replace(/^\\/+/, '');
        }
        return '';
      };

      const fromAnchors = Array.from(document.querySelectorAll('a[href*="amzn.to/"]'))
        .map((a) => clean(a.href))
        .filter(Boolean);
      const fromInputs = Array.from(document.querySelectorAll('input[value*="amzn.to/"], textarea'))
        .map((el) => clean(el.value || el.textContent || ''))
        .filter((v) => /amzn\\.to\\//i.test(v));
      const explicitSelectors = [
        '#amzn-ss-shortlink-textarea',
        '#amzn-ss-text-shortlink-textarea',
        'input[id*="shortlink"]',
        'textarea[id*="shortlink"]',
        'input[value*="amzn.to/"]',
      ];
      const fromSelectors = [];
      for (const sel of explicitSelectors) {
        const el = document.querySelector(sel);
        if (!el) continue;
        fromSelectors.push(clean(el.value || el.textContent || el.getAttribute('value') || ''));
      }
      const shortUrl = pick([...fromSelectors, ...fromInputs, ...fromAnchors]);
      return { shortUrl, candidateCount: fromAnchors.length + fromInputs.length + fromSelectors.length };
    }"""

    click_fn = """() => {
      const clean = (v) => (v || '').toString().replace(/\\s+/g, ' ').trim();
      const selectors = [
        '#amzn-ss-get-link',
        'a#amzn-ss-get-link',
        'button#amzn-ss-get-link',
        '[id*="amzn-ss-get-link"]',
        '[id*="siteStripeGetLink"]',
        '[aria-label*="Get Link"]',
        'a[href*="getlink"]',
      ];
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el) {
          el.click();
          return { clicked: true, selector: sel, text: clean(el.textContent || '') };
        }
      }
      const nodes = Array.from(document.querySelectorAll('a, button, span, div'));
      for (const node of nodes) {
        const txt = clean(node.textContent || '');
        if (!txt) continue;
        if (/^get\\s+link$/i.test(txt) || /get\\s+link/i.test(txt)) {
          const rect = node.getBoundingClientRect();
          if (rect.width < 8 || rect.height < 8) continue;
          node.click();
          return { clicked: true, selector: 'text:get link', text: txt };
        }
      }
      return { clicked: false };
    }"""

    for i in range(max(1, int(attempts))):
        extracted = _browser_eval(extract_fn, target_id, timeout_ms=30000)
        short_url = _normalize_sitestripe_short_url(str(extracted.get("shortUrl") or ""))
        if short_url:
            return {
                "ok": True,
                "short_url": short_url,
                "method": "direct" if i == 0 else "get_link_popup",
                "attempt": i + 1,
            }
        # Prefer OpenClaw agent-style UI interaction: snapshot -> ref click.
        clicked = _browser_click_get_link_from_snapshot(target_id)
        if not bool(clicked.get("clicked")):
            # Fallback to DOM click only when ref-based click doesn't find targets.
            clicked = _browser_eval(click_fn, target_id, timeout_ms=20000)
        if not bool(clicked.get("clicked")):
            break
        _browser_wait(900, target_id=target_id)

    return {
        "ok": False,
        "short_url": "",
        "error": "sitestripe_short_url_not_found",
    }


def _browser_scroll_for_reviews(target_id: str, loops: int = 9) -> dict[str, Any]:
    checkpoints: list[dict[str, Any]] = []
    for i in range(max(1, loops)):
        fn = """() => {
          const y = Math.max(200, Math.floor(window.innerHeight * 0.85));
          window.scrollBy({ top: y, left: 0, behavior: 'instant' });
          return { scrollY: window.scrollY, scrollHeight: document.documentElement.scrollHeight };
        }"""
        state = _browser_eval(fn, target_id, timeout_ms=20000)
        checkpoints.append(
            {
                "step": i + 1,
                "scrollY": int(state.get("scrollY") or 0),
                "scrollHeight": int(state.get("scrollHeight") or 0),
            }
        )
        _browser_wait(550, target_id=target_id)

    jump_reviews_fn = """() => {
      const selectors = [
        '#reviewsMedley',
        '#reviews-medley-footer',
        '#cm-cr-dp-review-list',
        '#customerReviews',
        '[data-hook="cr-filter-info-review-rating-count"]'
      ];
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el) {
          el.scrollIntoView({ behavior: 'instant', block: 'start' });
          return { jumped: true, selector: sel };
        }
      }
      return { jumped: false };
    }"""
    jumped = _browser_eval(jump_reviews_fn, target_id, timeout_ms=20000)
    _browser_wait(700, target_id=target_id)
    anchors = _browser_eval(
        """() => ({
          hasReviewsMedley: !!document.querySelector('#reviewsMedley'),
          hasReviewList: !!document.querySelector('#cm-cr-dp-review-list'),
          reviewNodeCount: document.querySelectorAll('[data-hook="review"]').length
        })""",
        target_id,
        timeout_ms=20000,
    )
    return {
        "checkpoints": checkpoints,
        "jumped": jumped,
        "anchors": anchors,
    }


def _browser_extract_page_data(target_id: str, max_reviews: int = 12) -> dict[str, Any]:
    fn = f"""() => {{
      const maxReviews = {int(max_reviews)};
      const clean = (v) => (v || '').toString().replace(/\\s+/g, ' ').trim();
      const toInt = (v) => {{
        const m = clean(v).match(/([0-9]{{1,3}}(?:,[0-9]{{3}})*)/);
        return m ? parseInt(m[1].replace(/,/g, ''), 10) : null;
      }};
      const toFloat = (v) => {{
        const m = clean(v).match(/([0-5](?:\\.[0-9])?)/);
        return m ? parseFloat(m[1]) : null;
      }};
      const text = (sel) => {{
        const el = document.querySelector(sel);
        return el ? clean(el.textContent || '') : '';
      }};
      const maybeText = (sel) => {{
        const el = document.querySelector(sel);
        if (!el) return '';
        return clean(el.getAttribute('title') || el.textContent || '');
      }};
      const fromSrcset = (srcset) => {{
        const raw = clean(srcset);
        if (!raw) return '';
        const parts = raw.split(',').map(x => clean(x)).filter(Boolean);
        if (!parts.length) return '';
        let best = parts[0].split(' ')[0];
        let bestW = 0;
        for (const p of parts) {{
          const [u, w] = p.split(' ');
          const ww = parseInt((w || '').replace(/[^0-9]/g, ''), 10) || 0;
          if (ww >= bestW) {{ bestW = ww; best = u; }}
        }}
        return clean(best);
      }};

      const pageTitle = clean(document.title || '');
      const robotCheck = /robot check|captcha/i.test(pageTitle)
        || !!document.querySelector('form[action*="validateCaptcha"], img[src*="captcha"], input[name*="captch"]');

      const productTitle = text('#productTitle') || text('#title') || text('h1');

      const priceCandidates = [
        text('#corePrice_feature_div .a-price .a-offscreen'),
        text('#corePriceDisplay_desktop_feature_div .a-price .a-offscreen'),
        text('#twister-plus-price-data-price'),
        text('#priceblock_dealprice'),
        text('#priceblock_ourprice'),
        text('[data-a-color="price"] .a-offscreen'),
        text('.apexPriceToPay .a-offscreen')
      ].filter(Boolean);

      const ratingText = maybeText('#acrPopover')
        || text('span[data-hook="rating-out-of-text"]')
        || text('#reviewsMedley .a-icon-alt')
        || text('#acrPopover .a-icon-alt');
      const reviewCountText = text('#acrCustomerReviewText')
        || text('[data-hook="total-review-count"]')
        || text('[data-hook="cr-filter-info-review-rating-count"]');

      const availability = text('#availability span') || text('#availability') || '';

      const bullets = Array.from(document.querySelectorAll('#feature-bullets li span, #feature-bullets li .a-list-item'))
        .map(el => clean(el.textContent || ''))
        .filter(v => v && v.length > 12);
      const aboutBullets = Array.from(new Set(bullets)).slice(0, 12);

      const specs = [];
      const pushSpec = (k, v) => {{
        const key = clean(k);
        const val = clean(v);
        if (!key || !val) return;
        if (key.length > 60 || val.length > 260) return;
        specs.push({{ key, value: val }});
      }};

      const specTableSelectors = [
        '#productDetails_techSpec_section_1 tr',
        '#productDetails_detailBullets_sections1 tr',
        '#productOverview_feature_div tr',
        '#technicalSpecifications_section_1 tr'
      ];

      for (const rowSel of specTableSelectors) {{
        document.querySelectorAll(rowSel).forEach(tr => {{
          const th = tr.querySelector('th, td:first-child');
          const td = tr.querySelector('td, td:last-child');
          if (!th || !td) return;
          pushSpec(th.textContent || '', td.textContent || '');
        }});
      }};

      document.querySelectorAll('#detailBullets_feature_div li, #detailBulletsWrapper_feature_div li').forEach(li => {{
        const txt = clean(li.textContent || '');
        const m = txt.match(/^([^:]+):\\s*(.+)$/);
        if (m) pushSpec(m[1], m[2]);
      }});

      const imageCandidates = [];
      const seenImage = new Set();
      const pushImage = (url, source, alt='') => {{
        const u = clean(url);
        if (!u || !/^https?:\\/\\//i.test(u)) return;
        if (seenImage.has(u)) return;
        seenImage.add(u);
        imageCandidates.push({{ url: u, source: clean(source), alt: clean(alt) }});
      }};

      const landing = document.querySelector('#landingImage, #imgTagWrapperId img');
      if (landing) {{
        pushImage(landing.getAttribute('data-old-hires') || '', 'landing:data-old-hires', landing.getAttribute('alt') || '');
        pushImage(landing.getAttribute('src') || '', 'landing:src', landing.getAttribute('alt') || '');
        pushImage(fromSrcset(landing.getAttribute('srcset') || ''), 'landing:srcset', landing.getAttribute('alt') || '');
      }}

      document.querySelectorAll('#altImages img, #altImages li img, img[data-old-hires], #imageBlock img').forEach((img, idx) => {{
        const alt = img.getAttribute('alt') || '';
        pushImage(img.getAttribute('data-old-hires') || '', `gallery:data-old-hires:${{idx}}`, alt);
        pushImage(img.getAttribute('src') || '', `gallery:src:${{idx}}`, alt);
        pushImage(fromSrcset(img.getAttribute('srcset') || ''), `gallery:srcset:${{idx}}`, alt);
      }});

      const reviews = [];
      const reviewNodes = document.querySelectorAll('#cm-cr-dp-review-list [data-hook="review"], [data-hook="review"]');
      for (const node of reviewNodes) {{
        if (reviews.length >= maxReviews) break;
        const titleNode = node.querySelector('[data-hook="review-title"], .review-title');
        const bodyNode = node.querySelector('[data-hook="review-body"] span, [data-hook="review-body"], .review-text-content span');
        const ratingNode = node.querySelector('[data-hook="review-star-rating"], [data-hook="cmps-review-star-rating"], .review-rating');
        const dateNode = node.querySelector('[data-hook="review-date"]');
        const verifiedNode = node.querySelector('[data-hook="avp-badge"]');
        const helpfulNode = node.querySelector('[data-hook="helpful-vote-statement"]');

        const title = clean(titleNode ? titleNode.textContent : '');
        const body = clean(bodyNode ? bodyNode.textContent : '');
        if (!body && !title) continue;

        reviews.push({{
          title,
          body,
          rating_text: clean(ratingNode ? (ratingNode.getAttribute('title') || ratingNode.textContent || '') : ''),
          rating_value: toFloat(ratingNode ? (ratingNode.getAttribute('title') || ratingNode.textContent || '') : ''),
          date: clean(dateNode ? dateNode.textContent : ''),
          verified_purchase: !!verifiedNode,
          helpful_text: clean(helpfulNode ? helpfulNode.textContent : ''),
          helpful_count: toInt(helpfulNode ? helpfulNode.textContent : '')
        }});
      }}

      const customersSay = Array.from(document.querySelectorAll('#cr-summarization-attributes-list span, [data-hook="cr-insights-widget"] span'))
        .map(el => clean(el.textContent || ''))
        .filter(v => v && v.length > 8)
        .slice(0, 30);

      return {{
        robotCheck,
        currentUrl: location.href,
        pageTitle,
        title: productTitle,
        availability,
        facts: {{
          price_candidates: priceCandidates,
          rating_text: ratingText,
          rating_value: toFloat(ratingText),
          review_count_text: reviewCountText,
          review_count_value: toInt(reviewCountText)
        }},
        about_bullets: aboutBullets,
        specs: specs.slice(0, 24),
        image_candidates: imageCandidates.slice(0, 120),
        reviews,
        customers_say: customersSay,
        scrape_meta: {{
          reviews_seen: reviewNodes.length,
          scrollY: window.scrollY,
          scrollHeight: document.documentElement.scrollHeight
        }}
      }};
    }}"""
    result = _browser_eval(fn, target_id, timeout_ms=70000)
    if not isinstance(result, dict):
        raise BrowserError("invalid_browser_extract_payload")
    return result


def _is_auth_or_interstitial_page(page_data: dict[str, Any]) -> bool:
    page_title = str(page_data.get("pageTitle") or "").lower()
    current_url = str(page_data.get("currentUrl") or "").lower()
    product_title = str(page_data.get("title") or "").lower()
    blockers = [
        "two-step verification",
        "sign in",
        "authentication required",
        "verify it's you",
        "verify it is you",
        "robot check",
        "captcha",
    ]
    if any(x in page_title for x in blockers):
        return True
    if any(x in product_title for x in blockers):
        return True
    if any(x in current_url for x in ["/ap/", "signin", "mfa", "challenge"]):
        return True
    return False


def _clean_text(text: str) -> str:
    t = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text or "")
    t = re.sub(r"`{1,3}", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _split_lines(text: str) -> list[str]:
    return [x.rstrip() for x in (text or "").splitlines()]


def _first_float(patterns: list[str], text: str) -> float | None:
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                continue
    return None


def _extract_rating(text: str) -> float | None:
    return _first_float(
        [
            r"([0-5](?:\.\d)?)\s*out of\s*5\s*stars",
            r"rating\s*[:\-]?\s*([0-5](?:\.\d)?)",
            r"([0-5](?:\.\d)?)\s*/\s*5",
        ],
        text,
    )


def _extract_reviews_count(text: str) -> int | None:
    patterns = [
        r"([\d,]+)\s+ratings?",
        r"([\d,]+)\s+global\s+ratings?",
        r"([\d,]+)\s+reviews?",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except Exception:
                continue
    return None


def _extract_price(text: str) -> str | None:
    matches = re.findall(r"\$\s?([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d{2})?)", text)
    candidates: list[tuple[float, str]] = []
    for raw in matches:
        num_txt = raw.replace(",", "")
        try:
            val = float(num_txt)
        except Exception:
            continue
        if 5.0 <= val <= 10000.0:
            candidates.append((val, f"${raw}"))
    return candidates[0][1] if candidates else None


def _capture_section(lines: list[str], headers: list[str], stop_headers: list[str], max_lines: int = 60) -> list[str]:
    idx = -1
    for i, line in enumerate(lines):
        ll = line.lower()
        if any(h in ll for h in headers):
            idx = i
            break
    if idx < 0:
        return []

    out: list[str] = []
    for line in lines[idx + 1 :]:
        ll = line.lower().strip()
        if ll.startswith("#") and out:
            break
        if any(s in ll for s in stop_headers):
            break
        if not ll:
            continue
        out.append(line)
        if len(out) >= max_lines:
            break
    return out


def _extract_about_bullets(markdown: str, max_items: int = 8) -> list[str]:
    lines = _split_lines(markdown)
    section = _capture_section(
        lines,
        headers=["about this item", "about this product", "highlights", "key features"],
        stop_headers=["product information", "customer reviews", "top reviews", "technical details", "customer questions"],
        max_lines=80,
    )
    bullets: list[str] = []

    for line in section:
        s = line.strip()
        if re.match(r"^[-*•]\s+", s):
            bullets.append(_clean_text(re.sub(r"^[-*•]\s+", "", s)))
        elif re.match(r"^\d+[.)]\s+", s):
            bullets.append(_clean_text(re.sub(r"^\d+[.)]\s+", "", s)))

    if not bullets and section:
        section_text = _clean_text(" ".join(section))
        for sent in re.split(r"(?<=[.!?])\s+", section_text):
            sent = sent.strip()
            if len(sent) >= 20:
                bullets.append(sent)

    dedup: list[str] = []
    seen: set[str] = set()
    for b in bullets:
        key = b.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(b)
        if len(dedup) >= max_items:
            break
    return dedup


def _extract_sentences(text: str, max_sentences: int = 2) -> list[str]:
    clean = _clean_text(text)
    if not clean:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    out: list[str] = []
    for sentence in sentences:
        s = sentence.strip(" -\t")
        if len(s) < 30:
            continue
        out.append(s)
        if len(out) >= max_sentences:
            break
    return out


def _window_around(text: str, marker: str, radius_after: int = 600) -> str:
    low = text.lower()
    idx = low.find(marker.lower())
    if idx < 0:
        return ""
    return text[idx : idx + radius_after]


def _extract_review_signals(markdown: str, max_snippets: int = 8) -> dict[str, Any]:
    positive: list[str] = []
    critical: list[str] = []
    evidence: list[str] = []

    pos_window = _window_around(markdown, "top positive review")
    crit_window = _window_around(markdown, "top critical review")
    customer_says_window = _window_around(markdown, "customers say")

    for sentence in _extract_sentences(pos_window, max_sentences=2):
        positive.append(sentence)
        evidence.append(sentence)
    for sentence in _extract_sentences(crit_window, max_sentences=2):
        critical.append(sentence)
        evidence.append(sentence)
    for sentence in _extract_sentences(customer_says_window, max_sentences=2):
        evidence.append(sentence)
        if any(x in sentence.lower() for x in NEGATIVE_MARKERS):
            critical.append(sentence)
        else:
            positive.append(sentence)

    for line in _split_lines(markdown):
        ll = line.lower()
        if "review" not in ll and "customers say" not in ll:
            continue
        sentence = _clean_text(line)
        if len(sentence) < 35:
            continue
        if any(x in ll for x in NEGATIVE_MARKERS):
            critical.append(sentence)
        else:
            positive.append(sentence)
        evidence.append(sentence)
        if len(evidence) >= max_snippets * 2:
            break

    def _dedup_trim(items: list[str], max_items: int) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in items:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(item[:320])
            if len(out) >= max_items:
                break
        return out

    return {
        "positive_snippets": _dedup_trim(positive, max_snippets),
        "critical_snippets": _dedup_trim(critical, max_snippets),
        "evidence_snippets": _dedup_trim(evidence, max_snippets),
    }


def _extract_review_signals_structured(reviews: list[dict[str, Any]], customers_say: list[str], max_snippets: int = 8) -> dict[str, Any]:
    positive: list[str] = []
    critical: list[str] = []
    evidence: list[str] = []

    for row in reviews:
        if not isinstance(row, dict):
            continue
        title = _clean_text(str(row.get("title") or ""))
        body = _clean_text(str(row.get("body") or ""))
        if not body and not title:
            continue
        text = f"{title}. {body}".strip(" .")
        text = text[:420]
        rating = row.get("rating_value")
        low = text.lower()

        if isinstance(rating, (int, float)):
            if float(rating) >= 4.0:
                positive.append(text)
            elif float(rating) <= 3.0:
                critical.append(text)
            else:
                if any(x in low for x in NEGATIVE_MARKERS):
                    critical.append(text)
                else:
                    positive.append(text)
        else:
            if any(x in low for x in NEGATIVE_MARKERS):
                critical.append(text)
            else:
                positive.append(text)
        evidence.append(text)

    for sentence in customers_say:
        s = _clean_text(sentence)
        if len(s) < 25:
            continue
        if any(x in s.lower() for x in NEGATIVE_MARKERS):
            critical.append(s)
        else:
            positive.append(s)
        evidence.append(s)

    def _dedup(items: list[str], max_items: int) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in items:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
            if len(out) >= max_items:
                break
        return out

    return {
        "positive_snippets": _dedup(positive, max_snippets),
        "critical_snippets": _dedup(critical, max_snippets),
        "evidence_snippets": _dedup(evidence, max_snippets),
    }


def _theme_counts(texts: list[str]) -> dict[str, int]:
    scores = {k: 0 for k in THEME_KEYWORDS}
    for text in texts:
        low = text.lower()
        for theme, words in THEME_KEYWORDS.items():
            for word in words:
                if word in low:
                    scores[theme] += 1
    return {k: v for k, v in scores.items() if v > 0}


def _top_themes(scores: dict[str, int], max_items: int = 4) -> list[str]:
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [k for k, _ in ordered[:max_items]]


def _looks_like_image_url(url: str) -> bool:
    low = url.lower()
    if not (low.startswith("http://") or low.startswith("https://")):
        return False
    if any(ext in low for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
        return True
    if "/images/" in low and "amazon" in low:
        return True
    if any(host in low for host in SAFE_IMAGE_HOST_KEYWORDS):
        return True
    return False


def _score_image_url(url: str, alt_text: str = "", source: str = "") -> tuple[int, list[str]]:
    low = url.lower()
    alt = (alt_text or "").lower()
    src = (source or "").lower()
    score = 0
    reasons: list[str] = []

    if any(host in low for host in SAFE_IMAGE_HOST_KEYWORDS):
        score += 45
        reasons.append("trusted_amazon_image_host")
    if "/images/i/" in low:
        score += 20
        reasons.append("amazon_gallery_path")
    if any(x in low for x in ["sl1500", "ac_sl", "_sx", "_sy", "_ux", "_uy", "_sl"]):
        score += 16
        reasons.append("likely_high_resolution")
    if "landing" in src:
        score += 12
        reasons.append("landing_image")
    if any(x in alt for x in ["wear", "using", "lifestyle", "desk", "setup", "in use"]):
        score += 10
        reasons.append("contextual_alt_text")
    if any(x in low for x in ["sprite", "logo", "icon", "thumb", "thumbnail", "video", "play-icon"]):
        score -= 40
        reasons.append("likely_non_primary_visual")

    return score, reasons


def _rank_image_candidates(markdown: str, links: list[Any], response: dict[str, Any], max_items: int) -> list[dict[str, Any]]:
    urls: list[str] = []
    urls.extend(re.findall(r"!\[[^\]]*\]\((https?://[^\s)]+)\)", markdown or ""))
    for item in links:
        if isinstance(item, str) and _looks_like_image_url(item):
            urls.append(item)
    if isinstance(response, dict):
        for val in response.values():
            if isinstance(val, str) and _looks_like_image_url(val):
                urls.append(val)

    seen: set[str] = set()
    ranked: list[dict[str, Any]] = []
    for url in urls:
        if not _looks_like_image_url(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        score, reasons = _score_image_url(url)
        if score < 0:
            continue
        ranked.append({"url": url, "score": score, "reasons": reasons})

    ranked.sort(key=lambda x: (-int(x["score"]), x["url"]))
    return ranked[: max(1, max_items)]


def _rank_structured_image_candidates(candidates: list[dict[str, Any]], max_items: int) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in candidates:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or not _looks_like_image_url(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        alt = str(item.get("alt") or "")
        source = str(item.get("source") or "")
        score, reasons = _score_image_url(url, alt_text=alt, source=source)
        if score < 0:
            continue
        ranked.append({
            "url": url,
            "score": score,
            "reasons": reasons,
            "alt": alt,
            "source": source,
        })
    ranked.sort(key=lambda x: (-int(x["score"]), x["url"]))
    return ranked[: max(1, max_items)]


def _choose_extension(url: str, content_type: str | None = None) -> str:
    if content_type:
        ct = content_type.lower()
        if "png" in ct:
            return ".png"
        if "webp" in ct:
            return ".webp"
        if "gif" in ct:
            return ".gif"
    low = url.lower()
    for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        if ext in low:
            return ext
    return ".jpg"


def _download_image(url: str, out_path_without_ext: Path, timeout_sec: int = 25) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "rayviewslab-market-scout/1.0"})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310
        content_type = str(resp.headers.get("Content-Type") or "").lower()
        data = resp.read()
    if not content_type.startswith("image/"):
        return {"ok": False, "error": f"unexpected_content_type:{content_type}"}
    if len(data) < 25000:
        return {"ok": False, "error": "image_too_small"}

    ext = _choose_extension(url, content_type)
    out_path = out_path_without_ext.with_suffix(ext)
    _write_bytes_atomic(out_path, data)
    return {
        "ok": True,
        "path": str(out_path),
        "bytes": len(data),
        "sha1": hashlib.sha1(data).hexdigest(),
        "content_type": content_type,
    }


def _build_script_brief(intel: dict[str, Any]) -> dict[str, Any]:
    facts = intel.get("facts", {})
    reviews = intel.get("reviews", {})
    themes = reviews.get("themes", {})
    affiliate = intel.get("affiliate", {}) if isinstance(intel.get("affiliate"), dict) else {}

    pros: list[str] = []
    pros.extend(intel.get("about_bullets", [])[:3])
    pros.extend(reviews.get("positive_snippets", [])[:2])

    cons = reviews.get("critical_snippets", [])[:2]
    if not cons:
        cons = ["Some buyers mention trade-offs; verify current review trends before buying."]

    evidence = reviews.get("evidence_snippets", [])[:3]

    return {
        "asin": intel.get("asin"),
        "title": intel.get("title"),
        "affiliate_short_url": affiliate.get("sitestripe_short_url"),
        "price": facts.get("price"),
        "rating": facts.get("rating"),
        "reviews_count": facts.get("reviews_count"),
        "top_positive_themes": themes.get("positive", []),
        "top_concern_themes": themes.get("concerns", []),
        "pros": pros,
        "cons": cons,
        "evidence": evidence,
        "visual_recommendations": [
            "Use one hero image showing full product body.",
            "Use one in-use/lifestyle angle showing context.",
            "Use one close-up for main differentiating feature.",
        ],
    }


def _emit_supabase_event(url: str, service_role_key: str, payload: dict[str, Any]) -> tuple[bool, str]:
    endpoint = url.rstrip("/") + "/rest/v1/ops_agent_events"
    body = json.dumps([payload], ensure_ascii=True).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Prefer": "return=minimal",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15):  # noqa: S310
            return True, "ok"
    except Exception as exc:
        return False, str(exc)


def _build_obsidian_note(intel: dict[str, Any], run_id: str, category: str) -> str:
    facts = intel.get("facts", {})
    reviews = intel.get("reviews", {})
    images = intel.get("downloaded_images", [])

    lines: list[str] = []
    lines.append(f"# {intel.get('title') or intel.get('asin')}")
    lines.append("")
    lines.append(f"- run_id: `{run_id}`")
    lines.append(f"- category: `{category}`")
    lines.append(f"- asin: `{intel.get('asin')}`")
    lines.append(f"- url: {intel.get('product_url')}")
    lines.append(f"- sitestripe_short_url: {((intel.get('affiliate') or {}).get('sitestripe_short_url') or 'n/a')}")
    lines.append(f"- rating: `{facts.get('rating')}`")
    lines.append(f"- reviews: `{facts.get('reviews_count')}`")
    lines.append(f"- price: `{facts.get('price')}`")
    lines.append(f"- availability: `{intel.get('availability')}`")
    lines.append("")

    lines.append("## Key Features")
    for bullet in intel.get("about_bullets", [])[:6]:
        lines.append(f"- {bullet}")
    lines.append("")

    lines.append("## Customer Signals")
    for item in reviews.get("positive_snippets", [])[:3]:
        lines.append(f"- Positive: {item}")
    for item in reviews.get("critical_snippets", [])[:3]:
        lines.append(f"- Critical: {item}")
    lines.append(f"- Review rows captured: `{len(reviews.get('rows') or [])}`")
    lines.append("")

    lines.append("## Theme Summary")
    lines.append(f"- Positive themes: {', '.join(reviews.get('themes', {}).get('positive', [])) or 'n/a'}")
    lines.append(f"- Concern themes: {', '.join(reviews.get('themes', {}).get('concerns', [])) or 'n/a'}")
    lines.append("")

    lines.append("## Image Refs")
    for img in images:
        lines.append(f"- {img.get('path')} ({img.get('bytes')} bytes)")
    lines.append("")

    lines.append("## Scroll Audit")
    anchors = (((intel.get("source_meta") or {}).get("scroll_audit") or {}).get("anchors") or {})
    lines.append(f"- has reviews medley: `{bool(anchors.get('hasReviewsMedley'))}`")
    lines.append(f"- has review list: `{bool(anchors.get('hasReviewList'))}`")
    lines.append(f"- review node count (DOM): `{anchors.get('reviewNodeCount')}`")
    lines.append("")

    lines.append("## Script Brief")
    brief = intel.get("script_brief", {})
    for pro in brief.get("pros", [])[:3]:
        lines.append(f"- Pro: {pro}")
    for con in brief.get("cons", [])[:2]:
        lines.append(f"- Con: {con}")
    for ev in brief.get("evidence", [])[:2]:
        lines.append(f"- Evidence: {ev}")

    return "\n".join(lines).strip() + "\n"


def _build_product_text_summary(intel: dict[str, Any]) -> str:
    facts = intel.get("facts", {}) if isinstance(intel.get("facts"), dict) else {}
    reviews = intel.get("reviews", {}) if isinstance(intel.get("reviews"), dict) else {}
    affiliate = intel.get("affiliate", {}) if isinstance(intel.get("affiliate"), dict) else {}
    lines: list[str] = []
    lines.append(f"TITLE: {intel.get('title')}")
    lines.append(f"ASIN: {intel.get('asin')}")
    lines.append(f"URL: {intel.get('product_url')}")
    lines.append(f"SITESTRIPE_SHORT_URL: {affiliate.get('sitestripe_short_url') or 'n/a'}")
    lines.append(f"PRICE: {facts.get('price') or 'n/a'}")
    lines.append(f"RATING: {facts.get('rating') or 'n/a'}")
    lines.append(f"REVIEWS_COUNT: {facts.get('reviews_count') or 'n/a'}")
    lines.append(f"AVAILABILITY: {intel.get('availability') or 'n/a'}")
    lines.append("")
    lines.append("FEATURE_BULLETS:")
    for bullet in (intel.get("about_bullets") or [])[:8]:
        lines.append(f"- {bullet}")
    lines.append("")
    lines.append("CUSTOMER_EVIDENCE_POSITIVE:")
    for item in (reviews.get("positive_snippets") or [])[:5]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("CUSTOMER_EVIDENCE_CRITICAL:")
    for item in (reviews.get("critical_snippets") or [])[:5]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("IMAGE_FILES:")
    for img in (intel.get("downloaded_images") or [])[:6]:
        lines.append(f"- {img.get('path')}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True) + "\n")


def _ensure_notes_readme(notes_root: Path) -> None:
    readme = notes_root / "README.md"
    if readme.exists():
        return
    content = (
        "# Amazon Intel Memory\n\n"
        "This folder stores product-page learning extracted from Amazon via OpenClaw browser.\n\n"
        "- `learning_loop.jsonl`: per-product signals used for future script quality\n"
        "- `runs.jsonl`: per-run status (success/failure reasons)\n"
        "- `<YYYY-MM-DD>/*.md`: Obsidian-ready notes for each product\n"
    )
    _write_text_atomic(readme, content)


def _collect_one_product(
    seed: ProductSeed,
    category: str,
    max_reviews: int,
    image_candidates: int,
    download_count: int,
    assets_dir: Path,
    raw_dir: Path,
    close_tab: bool,
    wait_on_robot_check_sec: int,
    require_sitestripe_shortlink: bool,
) -> dict[str, Any]:
    target_id = ""
    scroll_audit: dict[str, Any] = {}
    sitestripe_link: dict[str, Any] = {}
    try:
        target_id = _browser_open_product(seed.product_url)
        _browser_wait(1200, target_id=target_id)
        sitestripe_link = _browser_extract_sitestripe_short_url(target_id, attempts=3)
        if require_sitestripe_shortlink and not bool(sitestripe_link.get("ok")):
            raise RuntimeError("sitestripe_short_url_missing")
        scroll_audit = _browser_scroll_for_reviews(target_id, loops=9)
        page_data = _browser_extract_page_data(target_id, max_reviews=max_reviews)
        if bool(page_data.get("robotCheck")) and int(wait_on_robot_check_sec) > 0:
            _browser_wait(int(wait_on_robot_check_sec) * 1000, target_id=target_id)
            _browser_scroll_for_reviews(target_id, loops=5)
            page_data = _browser_extract_page_data(target_id, max_reviews=max_reviews)
    finally:
        if close_tab and target_id:
            _browser_close_tab(target_id)

    if bool(page_data.get("robotCheck")):
        raise RuntimeError("amazon_robot_check_detected")
    if _is_auth_or_interstitial_page(page_data):
        raise RuntimeError("amazon_auth_or_interstitial_detected")

    facts_raw = page_data.get("facts") if isinstance(page_data.get("facts"), dict) else {}
    price_candidates = facts_raw.get("price_candidates") if isinstance(facts_raw.get("price_candidates"), list) else []
    price_text = " | ".join(str(x) for x in price_candidates if str(x).strip())

    rating = facts_raw.get("rating_value")
    if rating is None:
        rating = _extract_rating(str(facts_raw.get("rating_text") or ""))

    reviews_count = facts_raw.get("review_count_value")
    if reviews_count is None:
        reviews_count = _extract_reviews_count(str(facts_raw.get("review_count_text") or ""))

    price = _extract_price(price_text)
    if not price:
        price = _extract_price(str(page_data))

    about_bullets = [
        _clean_text(str(x))
        for x in (page_data.get("about_bullets") if isinstance(page_data.get("about_bullets"), list) else [])
        if _clean_text(str(x))
    ][:12]

    specs = [x for x in (page_data.get("specs") if isinstance(page_data.get("specs"), list) else []) if isinstance(x, dict)][:24]
    reviews_rows = [x for x in (page_data.get("reviews") if isinstance(page_data.get("reviews"), list) else []) if isinstance(x, dict)][: max_reviews]
    customers_say = [
        _clean_text(str(x))
        for x in (page_data.get("customers_say") if isinstance(page_data.get("customers_say"), list) else [])
        if _clean_text(str(x))
    ][:24]

    review_signals = _extract_review_signals_structured(reviews_rows, customers_say, max_snippets=8)
    pos_theme_scores = _theme_counts(review_signals.get("positive_snippets", []) + about_bullets)
    neg_theme_scores = _theme_counts(review_signals.get("critical_snippets", []))

    ranked_images = _rank_structured_image_candidates(
        [x for x in (page_data.get("image_candidates") if isinstance(page_data.get("image_candidates"), list) else []) if isinstance(x, dict)],
        max_items=image_candidates,
    )

    asin_slug = _slug(seed.asin or f"rank{seed.rank}", fallback=f"rank{seed.rank}")
    raw_path = raw_dir / f"{asin_slug}.browser_extract.json"
    _write_text_atomic(raw_path, json.dumps(page_data, ensure_ascii=True, indent=2) + "\n")

    downloaded: list[dict[str, Any]] = []
    if download_count > 0:
        used = 0
        for candidate in ranked_images:
            if used >= download_count:
                break
            if used == 0:
                base_name = f"{asin_slug}_hero"
            elif used == 1:
                base_name = f"{asin_slug}_life"
            else:
                base_name = f"{asin_slug}_alt_{used + 1:02d}"
            result = _download_image(candidate["url"], assets_dir / base_name, timeout_sec=25)
            if not result.get("ok"):
                continue
            result["source_url"] = candidate["url"]
            result["score"] = candidate["score"]
            result["source"] = candidate.get("source")
            downloaded.append(result)
            used += 1

    intel = {
        "rank": seed.rank,
        "asin": seed.asin,
        "title": str(page_data.get("title") or seed.title).strip(),
        "category": category,
        "product_url": seed.product_url,
        "affiliate": {
            "sitestripe_short_url": sitestripe_link.get("short_url"),
            "status": "ok" if bool(sitestripe_link.get("ok")) else "missing",
            "error": sitestripe_link.get("error"),
        },
        "availability": str(page_data.get("availability") or "").strip(),
        "facts": {
            "price": price,
            "price_candidates": price_candidates,
            "rating": rating,
            "rating_text": facts_raw.get("rating_text"),
            "reviews_count": reviews_count,
            "review_count_text": facts_raw.get("review_count_text"),
        },
        "about_bullets": about_bullets,
        "specs": specs,
        "reviews": {
            **review_signals,
            "themes": {
                "positive": _top_themes(pos_theme_scores),
                "concerns": _top_themes(neg_theme_scores),
            },
            "rows": reviews_rows,
            "customers_say": customers_say,
        },
        "image_candidates": ranked_images,
        "downloaded_images": downloaded,
        "raw_extract_path": str(raw_path),
        "source_meta": {
            "scraped_at": _iso_now(),
            "extract_meta": page_data.get("scrape_meta") or {},
            "page_title": page_data.get("pageTitle"),
            "current_url": page_data.get("currentUrl"),
            "scroll_audit": scroll_audit,
        },
    }
    intel["script_brief"] = _build_script_brief(intel)
    return intel


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect deep product intelligence from Amazon pages via OpenClaw browser")
    parser.add_argument("--category", default="unspecified")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--out-dir", default="tmp/amazon_intel")
    parser.add_argument("--products-json", default="")
    parser.add_argument("--product-url", action="append", default=[])
    parser.add_argument("--max-reviews-per-product", type=int, default=12)
    parser.add_argument("--max-image-candidates", type=int, default=16)
    parser.add_argument("--download-image-count", type=int, default=3)
    parser.add_argument(
        "--allow-missing-sitestripe-shortlink",
        action="store_true",
        help="Do not fail product collection when SiteStripe short link is not found.",
    )
    parser.add_argument("--product-attempts", type=int, default=3)
    parser.add_argument(
        "--wait-on-robot-check-sec",
        type=int,
        default=0,
        help="If robot check appears, wait N seconds for manual solve before re-checking.",
    )
    parser.add_argument("--no-pre-cleanup", action="store_true", help="Do not close existing Amazon tabs before run.")
    parser.add_argument("--browser-profile", default="")
    parser.add_argument(
        "--browser-profiles",
        default="openclaw-test",
        help="Fallback order for browser profiles (comma-separated). Ignored when --browser-profile is set.",
    )
    parser.add_argument(
        "--keep-product-tabs",
        action="store_true",
        help="Keep Amazon tabs open after extraction (default closes tabs).",
    )
    parser.add_argument("--notes-dir", default="agents/market_scout/memory/amazon_intel")
    parser.add_argument("--emit-supabase-events", action="store_true")
    parser.add_argument("--supabase-url", default=os.getenv("SUPABASE_URL", ""))
    parser.add_argument("--supabase-service-role-key", default=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    global BROWSER_PROFILE
    explicit_profile = str(args.browser_profile or "").strip()
    if explicit_profile:
        profile_order = [explicit_profile]
    else:
        profile_order = [x.strip() for x in str(args.browser_profiles or "").split(",") if x.strip()]
        if not profile_order:
            profile_order = ["openclaw"]

    BROWSER_PROFILE = profile_order[0]
    run_id = str(args.run_id).strip() or datetime.now().astimezone().strftime("amazon-intel-%Y%m%d-%H%M%S")

    out_root = Path(args.out_dir).expanduser().resolve() / run_id
    raw_dir = out_root / "raw"
    assets_dir = out_root / "assets" / "ref"
    notes_root = Path(args.notes_dir).expanduser().resolve()

    seeds: list[ProductSeed] = []
    if args.products_json:
        seeds.extend(_parse_products_json(Path(args.products_json).expanduser().resolve()))
    if args.product_url:
        seeds.extend(_parse_product_urls(args.product_url))

    if not seeds:
        payload = {
            "ok": False,
            "error": "no_products",
            "hint": "Pass --products-json or one/more --product-url values",
        }
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return 2

    _browser_prepare()
    cleanup_meta = {"skipped": bool(args.no_pre_cleanup), "profiles": []}
    if not args.no_pre_cleanup:
        for profile in profile_order:
            BROWSER_PROFILE = profile
            try:
                _browser_prepare()
                item = _browser_cleanup_amazon_tabs(max_close=120)
                item["profile"] = profile
            except Exception as exc:
                item = {"profile": profile, "closed": 0, "error": str(exc)}
            cleanup_meta["profiles"].append(item)

    errors: list[dict[str, Any]] = []
    products: list[dict[str, Any]] = []

    for seed in seeds:
        last_error = "unknown_error"
        attempts = max(1, int(args.product_attempts))
        for profile in profile_order:
            BROWSER_PROFILE = profile
            _browser_prepare()
            for attempt in range(1, attempts + 1):
                try:
                    intel = _collect_one_product(
                        seed,
                        category=str(args.category).strip(),
                        max_reviews=max(6, int(args.max_reviews_per_product)),
                        image_candidates=max(4, int(args.max_image_candidates)),
                        download_count=max(0, int(args.download_image_count)),
                        assets_dir=assets_dir,
                        raw_dir=raw_dir,
                        close_tab=not bool(args.keep_product_tabs),
                        wait_on_robot_check_sec=max(0, int(args.wait_on_robot_check_sec)),
                        require_sitestripe_shortlink=not bool(args.allow_missing_sitestripe_shortlink),
                    )
                    intel["source_meta"]["browser_profile"] = profile
                    products.append(intel)
                    last_error = ""
                    break
                except Exception as exc:
                    last_error = f"[profile={profile}] {exc}"
                    if attempt < attempts:
                        subprocess.run(
                            [
                                "openclaw",
                                "browser",
                                "--json",
                                "--timeout",
                                "60000",
                                "--browser-profile",
                                BROWSER_PROFILE,
                                "start",
                            ],
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        time.sleep(min(8.0, 1.5 * attempt))
                    continue
            if not last_error:
                break
        if last_error:
            errors.append({"asin": seed.asin, "product_url": seed.product_url, "error": last_error})

    compact_pack = {
        "run_id": run_id,
        "generated_at": _iso_now(),
        "category": str(args.category).strip(),
        "products": [p.get("script_brief", {}) for p in products],
    }

    report = {
        "ok": len(products) > 0,
        "run_id": run_id,
        "generated_at": _iso_now(),
        "category": str(args.category).strip(),
        "source": "amazon_page_intel_browser",
        "products": products,
        "errors": errors,
        "compact_script_pack": compact_pack,
        "input_hash": _sha1_text(
            json.dumps(
                {
                    "category": args.category,
                    "products": [s.__dict__ for s in seeds],
                    "max_reviews_per_product": args.max_reviews_per_product,
                    "download_image_count": args.download_image_count,
                    "pre_cleanup": not args.no_pre_cleanup,
                    "profile_order": profile_order,
                },
                sort_keys=True,
                ensure_ascii=True,
            )
        ),
        "browser_cleanup": cleanup_meta,
    }

    out_root.mkdir(parents=True, exist_ok=True)
    report_path = out_root / "amazon_product_intel.json"
    compact_path = out_root / "script_input_compact.json"
    _write_text_atomic(report_path, json.dumps(report, ensure_ascii=True, indent=2) + "\n")
    _write_text_atomic(compact_path, json.dumps(compact_pack, ensure_ascii=True, indent=2) + "\n")

    learning_jsonl = notes_root / "learning_loop.jsonl"
    runs_jsonl = notes_root / "runs.jsonl"
    _ensure_notes_readme(notes_root)
    dated_dir = notes_root / datetime.now().astimezone().strftime("%Y-%m-%d")
    note_paths: list[str] = []
    text_summary_paths: list[str] = []

    for intel in products:
        note_name = f"{_slug(intel.get('asin') or 'unknown')}.md"
        note_path = dated_dir / note_name
        note_content = _build_obsidian_note(intel, run_id=run_id, category=str(args.category).strip())
        _write_text_atomic(note_path, note_content)
        note_paths.append(str(note_path))

        txt_name = f"{_slug(intel.get('asin') or 'unknown')}.txt"
        txt_path = out_root / "product_text" / txt_name
        txt_content = _build_product_text_summary(intel)
        _write_text_atomic(txt_path, txt_content)
        intel["product_text_path"] = str(txt_path)
        text_summary_paths.append(str(txt_path))

        _append_jsonl(
            learning_jsonl,
            {
                "ts": _iso_now(),
                "run_id": run_id,
                "category": str(args.category).strip(),
                "asin": intel.get("asin"),
                "title": intel.get("title"),
                "affiliate_short_url": ((intel.get("affiliate") or {}).get("sitestripe_short_url")),
                "rating": intel.get("facts", {}).get("rating"),
                "reviews_count": intel.get("facts", {}).get("reviews_count"),
                "positive_themes": intel.get("reviews", {}).get("themes", {}).get("positive", []),
                "concern_themes": intel.get("reviews", {}).get("themes", {}).get("concerns", []),
                "evidence": intel.get("reviews", {}).get("evidence_snippets", [])[:2],
                "images": [x.get("path") for x in intel.get("downloaded_images", [])],
            },
        )

    report["obsidian_notes"] = note_paths
    report["product_text_summaries"] = text_summary_paths
    report["learning_loop_jsonl"] = str(learning_jsonl)
    report["runs_jsonl"] = str(runs_jsonl)
    _append_jsonl(
        runs_jsonl,
        {
            "ts": _iso_now(),
            "run_id": run_id,
            "category": str(args.category).strip(),
            "ok": len(products) > 0 and not errors,
            "products_count": len(products),
            "errors_count": len(errors),
            "errors": errors[:3],
            "browser_cleanup": cleanup_meta,
        },
    )
    _write_text_atomic(report_path, json.dumps(report, ensure_ascii=True, indent=2) + "\n")

    supabase_emit = {"enabled": bool(args.emit_supabase_events), "sent": 0, "errors": []}
    if args.emit_supabase_events:
        supabase_url = str(args.supabase_url or "").strip()
        supabase_key = str(args.supabase_service_role_key or "").strip()
        if not supabase_url or not supabase_key:
            supabase_emit["errors"].append("missing_supabase_credentials")
        else:
            for intel in products:
                event = {
                    "agent_id": "market_scout",
                    "kind": "amazon_product_intel",
                    "title": f"Amazon intel {intel.get('asin')}",
                    "summary": (
                        f"{intel.get('title')} | rating={intel.get('facts', {}).get('rating')} "
                        f"reviews={intel.get('facts', {}).get('reviews_count')}"
                    )[:380],
                    "tags": [
                        "amazon",
                        "product_intel",
                        "browser",
                        str(args.category).strip(),
                        str(intel.get("asin") or "unknown"),
                    ],
                }
                ok, msg = _emit_supabase_event(supabase_url, supabase_key, event)
                if ok:
                    supabase_emit["sent"] += 1
                else:
                    supabase_emit["errors"].append(msg)

    report["supabase_emit"] = supabase_emit
    _write_text_atomic(report_path, json.dumps(report, ensure_ascii=True, indent=2) + "\n")

    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        print(f"OK run={run_id} products={len(products)} errors={len(errors)} report={report_path}")

    if not products:
        return 1
    if errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
