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

## Prevention

Before uploading ANY reference image:

1. Check if image contains objects besides the main product
2. If yes: crop out unwanted objects OR find an alternate Amazon image
3. Use Amazon listing gallery (multiple images available per product)
4. Prefer images with clean/white backgrounds
