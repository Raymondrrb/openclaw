---
description: Playwright "Sync API inside asyncio loop" crash when creating new instance per call. Fixed with shared session globals.
tags: [failure, playwright, asyncio, crash, session]
created: 2026-02-19
severity: critical
affected_tools: [playwright, dzine-browser]
fix: shared-session-pattern
---

# Playwright Asyncio Crash

## What Happened

First pipeline run: product 05_hero succeeded (first call). Product 05_usage1 crashed with:

```
playwright._impl._errors.Error: It looks like you are using Playwright Sync API inside the asyncio loop.
```

## Root Cause

Each `generate_product_faithful()` call was creating a new `sync_playwright().start()`. The second call detected an existing event loop from the first Playwright instance.

## Fix Applied

Module-level shared session globals. See [[../dzine/shared-session]] for full pattern.

After fix: all 18 images generated without crashes.

## Prevention

Never create multiple Playwright instances in the same process. Always use the shared session pattern for sequential browser automation calls.
