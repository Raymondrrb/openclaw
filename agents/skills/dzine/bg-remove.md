---
description: BG Remove — isolates product from background. Treats phones/accessories as foreground objects — crop them from reference first.
tags: [dzine, tool, bg-remove, preprocessing]
created: 2026-02-19
updated: 2026-02-19
status: proven
credits: 0
---

# BG Remove

Removes the background from an image, leaving the product with transparent background. Built into the Dzine canvas top action bar.

## Critical Behavior

BG Remove treats ALL foreground objects as "product" — including phones, remotes, accessories in the frame. It will NOT remove a phone that's next to the product; it will preserve it.

**Solution**: Crop phones/accessories from the reference image BEFORE uploading. See [[../learnings/2026-02-19-phone-removal]].

## When to Use

- Prerequisite for [[generative-expand]] workflow (though this workflow is deprecated for scene variation)
- Standalone background removal for clean product cutouts
- When [[product-background]] handles BG removal internally, you don't need to call this separately

## Automation

Automated in `tools/lib/dzine_browser.py` function `_bg_remove()`.
Called automatically by `generate_product_faithful()`.

## Timing

Typical: 5-9 seconds. No credits consumed (included in canvas operations).
