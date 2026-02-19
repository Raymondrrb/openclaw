---
description: Playwright shared session pattern — reuses browser instance across calls to prevent asyncio crash.
tags: [dzine, automation, playwright, session]
created: 2026-02-19
updated: 2026-02-19
status: proven
---

# Shared Session Pattern

Module-level globals `_session_pw`, `_session_browser`, `_session_context`, `_session_page`, `_session_should_close` maintain a single Playwright instance across multiple `generate_product_faithful()` calls.

## Why

Playwright's `sync_playwright().start()` fails with "Sync API inside asyncio loop" if called when a Playwright instance is already running. Each pipeline call that creates a new Playwright instance hits this on the 2nd+ call.

## Pattern

```python
_session_pw = None
_session_browser = None
_session_context = None
_session_page = None
_session_should_close = False

def generate_product_faithful(...):
    def _attempt():
        global _session_pw, _session_browser, _session_context, _session_page, _session_should_close
        if _session_context is None:
            browser, context, should_close, pw = connect_or_launch(headless=False)
            _session_pw = pw
            _session_browser = browser
            _session_context = context
            _session_should_close = should_close
        context = _session_context
        # ... use context ...
        # Only close the page, NOT the session
        finally:
            if page:
                page.close()
```

## Key Rules

1. Create session ONCE (first call)
2. Reuse `_session_context` for all subsequent calls
3. Close individual PAGES after each call, never the session
4. Session lives for the entire pipeline run

Code: `tools/lib/dzine_browser.py` line 2174-2264
