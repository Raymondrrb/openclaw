---
description: Defensive handling for Dzine tutorial, promo, and modal dialogs in UI automation.
tags: [dzine, automation, playwright, reliability]
created: 2026-02-19
updated: 2026-02-19
status: proven
---

# Dialog Handling

Dzine frequently opens overlays that block clicks. Every automation run should clear dialogs before and after key actions.

## Required Strategy

1. Run `close_all_dialogs()` immediately after page load.
2. Run it again after navigation events and image generation completion.
3. Verify target element is visible and enabled before click.

## Blocking Dialog Types

- Intro/tutorial popups
- Promo banners
- Cookie/consent modal layers
- Regenerate confirmation dialogs

## Reliability Rule

Treat unexpected modal reappearance as normal behavior, not an exception path.

## Failure Recovery

If click fails twice:

1. Capture screenshot
2. Re-run `close_all_dialogs()`
3. Re-resolve selector by visible text instead of stale coordinates

Reference crash pattern: [[../learnings/2026-02-19-playwright-crash]]
