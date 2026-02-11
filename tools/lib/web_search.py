"""Web search utility — Brave Search API with browser fallback.

Brave Search API: uses BRAVE_SEARCH_API_KEY if configured.
Fallback: drives the running Brave browser via CDP to Google Search.

Stdlib only (+ Playwright for browser fallback).
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchResult:
    title: str = ""
    url: str = ""
    description: str = ""


# ---------------------------------------------------------------------------
# Brave Search API
# ---------------------------------------------------------------------------


def _brave_api_search(query: str, *, count: int = 10) -> list[SearchResult]:
    """Search via Brave Search API (requires BRAVE_SEARCH_API_KEY)."""
    api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("BRAVE_SEARCH_API_KEY not set")

    params = urllib.parse.urlencode({"q": query, "count": count})
    url = f"https://api.search.brave.com/res/v1/web/search?{params}"

    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    })

    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    results = []
    for item in data.get("web", {}).get("results", [])[:count]:
        results.append(SearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            description=item.get("description", ""),
        ))
    return results


# ---------------------------------------------------------------------------
# Browser fallback (Google via Brave CDP)
# ---------------------------------------------------------------------------


def _browser_search(query: str, *, count: int = 10) -> list[SearchResult]:
    """Search via Google in the running Brave browser (CDP).

    Brave Search blocks CDP with PoW captcha, so we use Google instead.
    """
    from tools.lib.brave_profile import connect_or_launch

    browser, context, should_close, pw = connect_or_launch(headless=False)
    page = context.new_page()
    results: list[SearchResult] = []

    try:
        encoded = urllib.parse.quote_plus(query)
        page.goto(
            f"https://www.google.com/search?q={encoded}&hl=en",
            wait_until="domcontentloaded",
            timeout=20000,
        )
        page.wait_for_timeout(3000)

        # Google result links: anchor tags containing h3 inside #rso
        links = page.locator("#rso a:has(h3)")
        n = min(links.count(), count)

        for i in range(n):
            try:
                link = links.nth(i)
                href = link.get_attribute("href", timeout=2000) or ""

                # Skip Google internal links
                if not href.startswith("http") or "google.com" in href:
                    continue

                # Title from h3
                h3 = link.locator("h3").first
                title = h3.inner_text(timeout=2000).strip() if h3.count() > 0 else ""

                if not title:
                    continue

                # Description: walk up to the result container and find .VwiC3b
                desc = ""
                # The link is inside a result block; go up to find the snippet
                container = link.locator("xpath=ancestor::div[@data-snf or @class]").last
                desc_el = container.locator(".VwiC3b").first
                if desc_el.count() > 0:
                    desc = desc_el.inner_text(timeout=2000).strip()

                # Fallback: check sibling containers via data-snf="nke7rc"
                if not desc:
                    parent_block = link.locator("xpath=ancestor::div[contains(@class, 'N54PNb')]").first
                    if parent_block.count() > 0:
                        nke = parent_block.locator("[data-snf='nke7rc']").first
                        if nke.count() > 0:
                            desc = nke.inner_text(timeout=2000).strip()

                results.append(SearchResult(
                    title=title, url=href, description=desc,
                ))
            except Exception:
                continue
    except Exception as exc:
        print(f"[web_search] Browser search failed: {exc}", file=sys.stderr)
    finally:
        page.close()
        if should_close:
            context.close()
        pw.stop()

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def web_search(query: str, *, count: int = 10) -> list[SearchResult]:
    """Search the web. Uses Brave API if key is set, otherwise browser."""
    api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
    if api_key:
        try:
            return _brave_api_search(query, count=count)
        except Exception as exc:
            print(f"[web_search] API failed, falling back to browser: {exc}",
                  file=sys.stderr)

    return _browser_search(query, count=count)


def search_site(domain: str, query: str, *, count: int = 5) -> list[SearchResult]:
    """Search within a specific domain."""
    return web_search(f"site:{domain} {query}", count=count)
