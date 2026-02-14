"""Markdown-first web fetcher — uses Cloudflare "Markdown for Agents" when available.

Sends Accept: text/markdown content negotiation. If the server responds with
text/markdown, uses the clean markdown directly (massive token savings).
Falls back to HTML fetch + local conversion otherwise.

Captures token hints from x-markdown-tokens response header and persists
metadata alongside the fetched content as disk-backed artifacts.

Stdlib only — no external HTTP dependencies.

Usage:
    from lib.markdown_fetch import fetch_markdown, FetchResult

    result = fetch_markdown("https://example.com/product-review")
    print(result.text[:200])        # Clean text content
    print(result.method)            # "markdown" | "html" | "failed"
    print(result.token_estimate)    # From x-markdown-tokens header, or None

    # With artifact persistence (recommended for research pipelines)
    result = fetch_markdown(url, persist_to="artifacts/web/run_001")
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FetchResult:
    """Result of a markdown-first fetch attempt."""
    url: str
    text: str = ""
    method: str = "failed"          # "markdown" | "html" | "failed"
    content_type: str = ""
    token_estimate: int | None = None
    content_length: int = 0
    fetched_at: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    artifact_path: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.method != "failed" and len(self.text) > 0


# ---------------------------------------------------------------------------
# User agent
# ---------------------------------------------------------------------------

_USER_AGENT = (
    "Mozilla/5.0 (compatible; OpenClaw/1.0; "
    "+https://github.com/Raymondrrb/openclaw) "
    "AppleWebKit/537.36"
)

# Cloudflare recommends this UA pattern for agents requesting markdown:
_AGENT_USER_AGENT = (
    "OpenClaw-Agent/1.0 (Markdown-capable; "
    "+https://github.com/Raymondrrb/openclaw)"
)


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------

def _fetch_with_accept(
    url: str,
    *,
    accept: str = "text/markdown, text/html;q=0.9, */*;q=0.1",
    timeout: int = 15,
    use_agent_ua: bool = True,
) -> tuple[bytes | None, dict[str, str], str]:
    """Fetch URL with custom Accept header. Returns (body, headers, error)."""
    ua = _AGENT_USER_AGENT if use_agent_ua else _USER_AGENT
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": ua,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            body = resp.read()
            return body, headers, ""
    except urllib.error.HTTPError as exc:
        return None, {}, f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        return None, {}, str(exc)


def _decode_body(body: bytes, headers: dict[str, str]) -> str:
    """Decode response body using charset from Content-Type or default UTF-8."""
    ct = headers.get("content-type", "")
    charset = "utf-8"
    if "charset=" in ct:
        charset = ct.split("charset=")[-1].split(";")[0].strip()
    return body.decode(charset, errors="replace")


def _is_markdown_response(headers: dict[str, str]) -> bool:
    """Check if server responded with markdown content type."""
    ct = headers.get("content-type", "").lower()
    return "text/markdown" in ct or "text/x-markdown" in ct


def _parse_token_hint(headers: dict[str, str]) -> int | None:
    """Extract token estimate from x-markdown-tokens header."""
    raw = headers.get("x-markdown-tokens", "").strip()
    if raw and raw.isdigit():
        return int(raw)
    return None


# ---------------------------------------------------------------------------
# Minimal HTML → Markdown fallback (for non-Cloudflare sites)
# ---------------------------------------------------------------------------

def _html_to_markdown_minimal(html: str) -> str:
    """Basic HTML → text conversion. Uses page_reader's extractor if available."""
    try:
        from tools.lib.page_reader import html_to_text
        return html_to_text(html)
    except ImportError:
        pass
    # Inline fallback: strip tags, keep text
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# URL → filesystem slug
# ---------------------------------------------------------------------------

def _url_to_slug(url: str, max_len: int = 80) -> str:
    """Convert URL to a safe filesystem slug."""
    parsed = urllib.parse.urlparse(url)
    parts = parsed.netloc.replace("www.", "") + parsed.path
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", parts)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:max_len] if slug else "page"


# ---------------------------------------------------------------------------
# Artifact persistence
# ---------------------------------------------------------------------------

def _persist_artifact(
    result: FetchResult,
    persist_dir: str | Path,
) -> Path:
    """Save fetched content and metadata to disk. Returns the markdown file path."""
    out_dir = Path(persist_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    slug = _url_to_slug(result.url)

    # Save markdown/text content
    md_path = out_dir / f"{slug}.md"
    md_path.write_text(result.text, encoding="utf-8")

    # Save metadata
    meta = {
        "url": result.url,
        "method": result.method,
        "content_type": result.content_type,
        "token_estimate": result.token_estimate,
        "content_length": result.content_length,
        "fetched_at": result.fetched_at,
        "artifact_path": str(md_path),
    }
    meta_path = out_dir / f"{slug}.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    result.artifact_path = str(md_path)
    return md_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_markdown(
    url: str,
    *,
    timeout: int = 15,
    persist_to: str | Path | None = None,
    min_content_len: int = 200,
    cache: Any = None,
) -> FetchResult:
    """Fetch a URL preferring markdown via content negotiation.

    Strategy:
    0. Check cache — if hit with valid TTL, return immediately (zero HTTP)
    1. Request with Accept: text/markdown — if server returns markdown, use it
    2. If server returns HTML, convert locally
    3. Store result in cache for future reuse
    4. Return FetchResult with method, token hints, and optional disk path

    Args:
        url: The page to fetch.
        timeout: HTTP timeout in seconds.
        persist_to: Directory to save .md + .json artifacts. None = no persist.
        min_content_len: Minimum text length to consider the fetch successful.
        cache: Optional FetchCache instance. Enables cache lookup + storage.

    Returns:
        FetchResult with .text, .method, .token_estimate, etc.
    """
    # ── Check cache first ─────────────────────────────────────────────
    if cache is not None:
        entry = cache.get(url)
        if entry is not None:
            cached_text = cache.get_text(url)
            if cached_text and len(cached_text) >= min_content_len:
                result = FetchResult(
                    url=url,
                    text=cached_text,
                    method=f"cached:{entry.method}",
                    content_type=entry.content_type,
                    token_estimate=entry.token_estimate,
                    content_length=entry.content_length,
                    fetched_at=entry.fetched_at,
                )
                if persist_to:
                    _persist_artifact(result, persist_to)
                return result

    result = FetchResult(
        url=url,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )

    # ── Attempt 1: markdown-first via content negotiation ─────────────
    body, headers, error = _fetch_with_accept(
        url,
        accept="text/markdown, text/html;q=0.9, */*;q=0.1",
        timeout=timeout,
    )

    if error:
        result.error = error
        result.method = "failed"
        print(f"  [md_fetch] FAIL {url}: {error}", file=sys.stderr)
        return result

    result.headers = headers
    result.content_type = headers.get("content-type", "")
    result.token_estimate = _parse_token_hint(headers)
    result.content_length = len(body) if body else 0

    if body and _is_markdown_response(headers):
        # Server gave us markdown directly — best case
        text = _decode_body(body, headers)
        if len(text) >= min_content_len:
            result.text = text
            result.method = "markdown"
            if cache is not None:
                cache.put_result(result)
            if persist_to:
                _persist_artifact(result, persist_to)
            return result

    # ── Attempt 2: HTML fallback — convert locally ────────────────────
    if body:
        ct = headers.get("content-type", "").lower()
        if "text/html" in ct or "xhtml" in ct:
            html = _decode_body(body, headers)
            text = _html_to_markdown_minimal(html)
            if len(text) >= min_content_len:
                result.text = text
                result.method = "html"
                if cache is not None:
                    cache.put_result(result)
                if persist_to:
                    _persist_artifact(result, persist_to)
                return result

    result.method = "failed"
    result.error = result.error or "Content too short or unsupported type"
    return result


def fetch_markdown_batch(
    urls: list[str],
    *,
    persist_to: str | Path | None = None,
    timeout: int = 15,
    cache: Any = None,
    parallel: bool = True,
    max_workers: int = 4,
) -> list[FetchResult]:
    """Fetch multiple URLs with markdown preference.

    Args:
        parallel: Use ThreadPoolExecutor for concurrent fetches (default True).
        max_workers: Max concurrent threads (default 4, capped to len(urls)).
    """
    if not parallel or len(urls) <= 1:
        return [
            fetch_markdown(url, persist_to=persist_to, timeout=timeout, cache=cache)
            for url in urls
        ]

    from concurrent.futures import ThreadPoolExecutor, as_completed

    workers = min(max_workers, len(urls))
    results: list[FetchResult | None] = [None] * len(urls)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_idx = {
            pool.submit(
                fetch_markdown,
                url,
                persist_to=persist_to,
                timeout=timeout,
                cache=cache,
            ): i
            for i, url in enumerate(urls)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                results[idx] = FetchResult(
                    url=urls[idx],
                    method="failed",
                    error=f"Thread error: {exc}",
                )

    return results  # type: ignore[return-value]
