# Markdown for Agents

## Overview

Our research pipeline uses **Cloudflare "Markdown for Agents"** content negotiation
to fetch web pages as clean markdown instead of raw HTML. This dramatically cuts
token usage — a typical review page drops from ~50K tokens (HTML) to ~2K tokens (markdown).

## How it works

1. HTTP request sends `Accept: text/markdown, text/html;q=0.9`
2. If the server (via Cloudflare) returns `Content-Type: text/markdown`, we use it directly
3. Otherwise, we fall back to HTML and convert locally
4. Token hints from `x-markdown-tokens` header guide chunking decisions

## Fetch pipeline (cost-ordered)

```
fetch_page_text(url, cache=cache)
  │
  ├─ 0. Cache lookup            ← FREE (lib/fetch_cache.py)
  │     URL+hash match → return cached text, zero HTTP
  │
  ├─ 1. Markdown negotiation   ← cheapest HTTP (lib/markdown_fetch.py)
  │     Accept: text/markdown
  │     → if text/markdown response: use directly
  │     → if text/html response: convert locally
  │     → store in cache for next time
  │
  ├─ 2. HTTP HTML fetch         ← standard (lib/page_reader.py)
  │     → html_to_text()
  │
  └─ 3. Playwright browser      ← most expensive
        → JS-rendered HTML → html_to_text()
```

## Usage

### Direct fetch

```python
from lib.markdown_fetch import fetch_markdown

result = fetch_markdown("https://example.com/review")
print(result.method)          # "markdown" | "html" | "cached:markdown" | "failed"
print(result.token_estimate)  # from x-markdown-tokens header
print(result.text[:200])      # clean content
```

### With artifact persistence

```python
result = fetch_markdown(url, persist_to="artifacts/web/run_001")
# Creates:
#   artifacts/web/run_001/example_com_review.md   (content)
#   artifacts/web/run_001/example_com_review.json (metadata)
```

### With cache (recommended for pipelines)

```python
from lib.fetch_cache import FetchCache
from lib.markdown_fetch import fetch_markdown

cache = FetchCache()                          # default: <repo>/.cache/fetch/, TTL=24h
cache = FetchCache(ttl_hours=48)              # custom TTL
cache = FetchCache(cache_dir="./my_cache")    # custom location

# First call: HTTP fetch + store in cache
result = fetch_markdown(url, cache=cache)     # method="markdown"

# Second call: instant from cache, zero HTTP
result = fetch_markdown(url, cache=cache)     # method="cached:markdown"
```

### Via page_reader (auto-integrated)

```python
from lib.fetch_cache import FetchCache
from lib.page_reader import fetch_page_text

cache = FetchCache()
text, method = fetch_page_text("https://example.com/review", cache=cache)
# method is now "markdown", "html", "cached:markdown", "cached:html", or "browser"
```

### Batch fetch

```python
from lib.markdown_fetch import fetch_markdown_batch

results = fetch_markdown_batch([url1, url2, url3], persist_to="artifacts/web/run_001")
for r in results:
    print(f"{r.url}: {r.method}, tokens={r.token_estimate}")
```

## FetchResult fields

| Field | Type | Description |
|-------|------|-------------|
| `url` | str | Fetched URL |
| `text` | str | Clean text content |
| `method` | str | `"markdown"`, `"html"`, `"cached:markdown"`, `"cached:html"`, or `"failed"` |
| `content_type` | str | Response Content-Type |
| `token_estimate` | int/None | From `x-markdown-tokens` header |
| `content_length` | int | Raw response size in bytes |
| `fetched_at` | str | ISO-8601 timestamp |
| `artifact_path` | str/None | Path to saved .md file (if persisted) |
| `ok` | bool | True if method != "failed" and text is non-empty |

## Token hints

When `x-markdown-tokens` is present, use it to decide:

- **< 2000 tokens**: Process inline, no chunking needed
- **2000–8000 tokens**: Single-pass extraction
- **> 8000 tokens**: Chunk into sections, summarize each, then merge

## Cache (lib/fetch_cache.py)

Disk-backed URL cache with TTL. Avoids redundant HTTP requests across runs.

### How it works

- Keyed by URL (SHA-256 hash)
- Stores content hash (SHA-256 of text) for change detection
- Configurable TTL per-cache or per-entry
- Index persists as `index.json`, content as individual `.md` files
- Automatic cleanup of stale entries

### Cache directory layout

```
.cache/fetch/
  index.json              # {url_key: metadata}
  content/
    a1b2c3d4e5f6g7h8.md  # cached page text
    ...
```

### Cache management

```python
from lib.fetch_cache import FetchCache

cache = FetchCache(ttl_hours=24)

# Check if content changed since last fetch
if cache.has_changed(url, new_text):
    # Re-extract evidence (content is different)
    ...

# Manual invalidation
cache.invalidate(url)

# Evict all expired entries
removed = cache.evict_expired()

# Stats
print(cache.stats())
# {"total_entries": 12, "active_entries": 10, "expired_entries": 2, ...}

# Clear everything
cache.clear()
```

### Recommended TTLs

| Content type | TTL | Rationale |
|---|---|---|
| Review articles | 24-48h | Updated infrequently |
| Product pages | 12-24h | Prices may change |
| Documentation | 72h | Very stable |
| News/blogs | 6-12h | May update same-day |

## Testing

```bash
# Markdown fetch tests (20 unit + 3 live)
python3 tools/test_markdown_fetch.py
python3 tools/test_markdown_fetch.py --live

# Cache tests (30 unit + 1 live)
python3 tools/test_fetch_cache.py
python3 tools/test_fetch_cache.py --live
```

### Live test results (Feb 2026)

| Metric | HTTP | Cache | Speedup |
|---|---|---|---|
| Cloudflare blog | 1.3s | 0.0s | ~3000x |
| Content | 557 bytes markdown | cached | identical |

## Sites with known support

Sites behind Cloudflare with "Markdown for Agents" enabled will respond with
`text/markdown`. As of Feb 2026, this includes Cloudflare's own blog and docs,
plus any domain where the site owner has enabled the feature.

Sites like NYT/Wirecutter, RTINGS, and PCMag currently return HTML — our
fallback converter handles these automatically.
