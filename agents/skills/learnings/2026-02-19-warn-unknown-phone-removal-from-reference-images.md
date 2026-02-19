---
description: "BG Remove classifies all foreground objects as "product" — it can't distinguish between the main product and accessories in the frame. → Two strategies, both successful:

### Strategy 1: Crop reference (products 01, 04, 05)

Used ffmpeg to crop the phone out before uploading:

```bash
/opt/homebrew/bin/ffmpeg -i original.jpg -vf "crop="
tags: [learning, learning, learning-event, warn, unknown]
created: 2026-02-19
severity: warn
video_id: vtest-qa
affected_tools: []
fix: Two strategies, both successful:

### Strategy 1: Crop reference (products 01, 04, 05)

Used ffmpeg to crop the phone out before uploading:

```bash
/opt/homebrew/bin/ffmpeg -i original.jpg -vf "crop=
---

# [WARN] unknown: Phone Removal from Reference Images

## Symptom

Phone Removal from Reference Images

## Root Cause

BG Remove classifies all foreground objects as "product" — it can't distinguish between the main product and accessories in the frame.

## Fix Applied

Two strategies, both successful:

### Strategy 1: Crop reference (products 01, 04, 05)

Used ffmpeg to crop the phone out before uploading:

```bash
/opt/homebrew/bin/ffmpeg -i original.jpg -vf "crop=

```
