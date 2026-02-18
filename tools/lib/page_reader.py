"""Fetch and extract text content from web pages.

Cheapest method first:
1. Markdown via content negotiation (Cloudflare "Markdown for Agents")
2. HTTP fetch via urllib (works for most review sites)
3. Playwright browser fallback (for dynamic/JS-required pages)

Returns clean text suitable for product extraction.
Stdlib only (+ optional Playwright).
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


# ---------------------------------------------------------------------------
# HTML → text
# ---------------------------------------------------------------------------

_SKIP_TAGS = frozenset({
    "script", "style", "noscript", "svg", "path", "meta", "link",
    "nav", "footer", "header", "aside", "iframe", "form", "button",
    "input", "select", "textarea", "img",
})

_BLOCK_TAGS = frozenset({
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "tr", "td", "th", "br", "hr", "blockquote",
    "section", "article", "main", "figure", "figcaption",
    "dt", "dd", "pre", "address",
})


class _TextExtractor(HTMLParser):
    """Strip HTML tags and return readable text."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs):
        tag_lower = tag.lower()
        if tag_lower in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag_lower in _BLOCK_TAGS and self._skip_depth == 0:
            self._parts.append("\n")

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if tag_lower in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag_lower in _BLOCK_TAGS and self._skip_depth == 0:
            self._parts.append("\n")

    def handle_data(self, data: str):
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        raw = "".join(self._parts)
        # Collapse whitespace within lines, keep line breaks
        lines = []
        for line in raw.splitlines():
            line = re.sub(r"[ \t]+", " ", line).strip()
            if line:
                lines.append(line)
        return "\n".join(lines)


def html_to_text(html: str) -> str:
    """Convert HTML to readable text, skipping scripts/nav/etc."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.get_text()


# ---------------------------------------------------------------------------
# Heading extraction — preserves H2/H3 structure from HTML
# ---------------------------------------------------------------------------

_HEADING_TAGS = frozenset({"h2", "h3"})

# Sections whose headings are not product picks
_HEADING_SKIP_PARENTS = frozenset({
    "nav", "footer", "header", "aside",
})


class _HeadingExtractor(HTMLParser):
    """Extract text of <h2> and <h3> elements, skipping nav/footer/etc."""

    def __init__(self):
        super().__init__()
        self._headings: list[tuple[str, str]] = []  # (tag, text)
        self._in_heading: str = ""
        self._current_text: list[str] = []
        self._skip_depth: int = 0

    def handle_starttag(self, tag: str, attrs):
        tag_lower = tag.lower()
        if tag_lower in _HEADING_SKIP_PARENTS:
            self._skip_depth += 1
        elif tag_lower in _HEADING_TAGS and self._skip_depth == 0:
            self._in_heading = tag_lower
            self._current_text = []

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if tag_lower in _HEADING_SKIP_PARENTS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag_lower == self._in_heading:
            text = " ".join("".join(self._current_text).split()).strip()
            if text:
                self._headings.append((self._in_heading, text))
            self._in_heading = ""
            self._current_text = []

    def handle_data(self, data: str):
        if self._in_heading:
            self._current_text.append(data)

    def get_headings(self) -> list[tuple[str, str]]:
        return list(self._headings)


def extract_headings(html: str) -> list[tuple[str, str]]:
    """Extract (tag, text) pairs for all <h2>/<h3> elements in *html*.

    Skips headings inside <nav>, <footer>, <header>, <aside>.
    """
    parser = _HeadingExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.get_headings()


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _http_fetch(url: str, *, timeout: int = 15) -> str | None:
    """Fetch page HTML via urllib. Returns None on failure."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ct = resp.headers.get("Content-Type", "")
            if "text/html" not in ct and "xhtml" not in ct:
                return None
            data = resp.read()
            # Detect encoding
            charset = "utf-8"
            if "charset=" in ct:
                charset = ct.split("charset=")[-1].split(";")[0].strip()
            return data.decode(charset, errors="replace")
    except Exception as exc:
        print(f"  [page_reader] HTTP fetch failed for {url}: {exc}", file=sys.stderr)
        return None


def _browser_fetch(url: str) -> str | None:
    """Fetch page HTML via Playwright/Brave CDP. Returns None on failure.

    Uses with_retry for transient errors (timeout, network).
    """
    try:
        from tools.lib.brave_profile import connect_or_launch
    except ImportError:
        return None

    try:
        browser, context, should_close, pw = connect_or_launch(headless=False)
        page = context.new_page()
        try:
            from tools.lib.retry import with_retry

            def _goto():
                page.goto(url, wait_until="domcontentloaded", timeout=20000)

            try:
                with_retry(_goto, max_retries=2, base_delay_s=2.0)
            except Exception as exc:
                print(f"  [page_reader] Browser fetch failed for {url}: {exc}", file=sys.stderr)
                return None

            page.wait_for_timeout(2000)
            html = page.content()
            return html
        except Exception as exc:
            print(f"  [page_reader] Browser fetch failed for {url}: {exc}", file=sys.stderr)
            return None
        finally:
            page.close()
            if should_close:
                context.close()
            pw.stop()
    except Exception as exc:
        print(f"  [page_reader] Browser init failed: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_page_text(
    url: str,
    *,
    persist_to: str | Path | None = None,
    cache: object | None = None,
) -> tuple[str, str]:
    """Fetch a page and return (text_content, method_used).

    Cost-ordered pipeline:
    0. Cache lookup (free — no HTTP at all)
    1. Markdown via content negotiation (cheapest HTTP)
    2. HTTP HTML fetch + local conversion
    3. Playwright browser fallback (most expensive)

    Returns ("", "failed") if all methods fail.

    Args:
        url: Page URL to fetch.
        persist_to: Optional dir path to save .md + .json artifacts.
        cache: Optional FetchCache instance for TTL-based caching.
    """
    # 1. Try markdown-first with cache (Cloudflare "Markdown for Agents")
    try:
        from tools.lib.markdown_fetch import fetch_markdown
        result = fetch_markdown(url, persist_to=persist_to, cache=cache)
        if result.ok and len(result.text) > 200:
            return result.text, result.method  # "markdown", "html", or "cached:*"
    except ImportError:
        pass
    except Exception as exc:
        print(f"  [page_reader] Markdown fetch error: {exc}", file=sys.stderr)

    # 2. Try HTTP HTML fetch
    html = _http_fetch(url)
    if html and len(html) > 500:
        text = html_to_text(html)
        if len(text) > 200:
            return text, "http"

    # 3. Fall back to browser
    html = _browser_fetch(url)
    if html and len(html) > 500:
        text = html_to_text(html)
        if len(text) > 200:
            return text, "browser"

    return "", "failed"


def fetch_page_data(
    url: str,
    *,
    persist_to: str | Path | None = None,
    cache: object | None = None,
) -> tuple[str, str, str | None]:
    """Fetch a page and return (text, method, raw_html).

    Same cost-ordered pipeline as ``fetch_page_text`` but also preserves
    the raw HTML when the fetch method produces it (HTTP or browser).
    Markdown-first methods return *raw_html=None* because no HTML is
    available in that path.
    """
    # 1. Markdown-first (no raw HTML available)
    try:
        from tools.lib.markdown_fetch import fetch_markdown
        result = fetch_markdown(url, persist_to=persist_to, cache=cache)
        if result.ok and len(result.text) > 200:
            return result.text, result.method, None
    except ImportError:
        pass
    except Exception as exc:
        print(f"  [page_reader] Markdown fetch error: {exc}", file=sys.stderr)

    # 2. HTTP HTML fetch — keep raw HTML
    html = _http_fetch(url)
    if html and len(html) > 500:
        text = html_to_text(html)
        if len(text) > 200:
            return text, "http", html

    # 3. Browser fallback — keep raw HTML
    html = _browser_fetch(url)
    if html and len(html) > 500:
        text = html_to_text(html)
        if len(text) > 200:
            return text, "browser", html

    return "", "failed", None
