---
description: BG Remove preserves phones/accessories as foreground. Must crop from reference image before upload.
tags: [failure, bg-remove, phone, preprocessing]
created: 2026-02-19
severity: medium
video_id: vtest-qa
affected_tools: [bg-remove]
fix: crop-reference-image
---

# Phone Removal from Reference Images

## What Happened

Amazon product photos for robot vacuums (products 01, 02, 04, 05) included a smartphone in the frame (showing the app). BG Remove treated the phone as part of the foreground product and preserved it.

## Root Cause

BG Remove classifies all foreground objects as "product" — it can't distinguish between the main product and accessories in the frame.

## Fix Applied

Two strategies, both successful:

### Strategy 1: Crop reference (products 01, 04, 05)

Used ffmpeg to crop the phone out before uploading:

```bash
/opt/homebrew/bin/ffmpeg -i original.jpg -vf "crop=iw*0.8:ih:0:0" cropped.jpg
```

Originals preserved in `amazon/cropped/` directory.

### Strategy 2: Alternate Amazon image (product 02 — Tapo)

The Tapo RV30 had a phone too close to the product to crop cleanly.
Found alternate Amazon image `41PRqyHoCtL` (robot + dock only, white BG, no phone).
Replaced 02_ref.jpg entirely.

## QA Verification (post-generation)

Even after cropping, product 01 STILL had phone remnants in all 5 variants (worst in mood — full phone with amber screen visible). The crop was not aggressive enough.

**Lesson:** After crop + BG Remove, ALWAYS visually verify the cutout before feeding into Product Background. If any phone edge/shape persists, re-crop more aggressively or use alternate Amazon image.

## Prevention

Before uploading ANY reference image:

1. Check if image contains objects besides the main product
2. If yes: crop out unwanted objects OR find an alternate Amazon image
3. Use Amazon listing gallery (multiple images available per product)
4. Prefer images with clean/white backgrounds
5. **After BG Remove, verify cutout is clean** — check edges for phone shapes, rectangular remnants, translucent strips
6. **If phone persists after crop** — use alternate Amazon image entirely (don't try incremental crops)
