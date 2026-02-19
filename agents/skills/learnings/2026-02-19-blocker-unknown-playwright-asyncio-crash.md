---
description: "Each `generate_product_faithful()` call was creating a new `sync_playwright().start()`. The second call detected an existing event loop from the first Playwright instance. → Module-level shared session globals. See [[../dzine/shared-session]] for full pattern.

After fix: all 18 images generated without crashes."
tags: [learning, learning, learning-event, blocker, unknown]
created: 2026-02-19
severity: blocker
video_id: 
affected_tools: []
fix: Module-level shared session globals. See [[../dzine/shared-session]] for full pattern.

After fix: all 18 images generated without crashes.
---

# [BLOCKER] unknown: Playwright Asyncio Crash

## Symptom

Playwright Asyncio Crash

## Root Cause

Each `generate_product_faithful()` call was creating a new `sync_playwright().start()`. The second call detected an existing event loop from the first Playwright instance.

## Fix Applied

Module-level shared session globals. See [[../dzine/shared-session]] for full pattern.

After fix: all 18 images generated without crashes.
