---
description: Product Background requires BG Remove as prerequisite — shows "Background is NOT empty" error otherwise.
tags: [learning, dzine, product-background, bg-remove, prerequisite]
created: 2026-02-19
updated: 2026-02-19
severity: high
status: fixed
---

# 2026-02-19 — BG Remove Prerequisite for Product Background

## Incident

Product Background generation timed out at 43% progress. A dialog appeared: "Background is NOT empty. The background must be empty."

## Root Cause

Product Background does NOT handle BG removal internally (contrary to initial assumption from Dzine marketing). It requires the image to already have a transparent/empty background before it will generate a new scene.

## Fix Applied

1. Updated `generate_product_faithful()` to run `_bg_remove()` before `_product_background()`
2. Added "Done" to `close_all_dialogs()` dismiss texts to handle the error dialog
3. After fix: 4 result images generated successfully in ~15-30s

## Correct Flow

```
Create Project → BG Remove → Product Background (Prompt tab → Manual Prompt → textarea → Generate)
```

## Prevention Rule

Always run BG Remove before Product Background. Never assume a Dzine tool handles preprocessing internally.

## Related Nodes

- [[../dzine/product-background]]
- [[../dzine/bg-remove]]
- [[2026-02-19-identical-images]]
