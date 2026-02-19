---
description: "Product Background does NOT handle BG removal internally (contrary to initial assumption from Dzine marketing). It requires the image to already have a transparent/empty background before it will gene → 1. Updated `generate_product_faithful()` to run `_bg_remove()` before `_product_background()`
2. Added "Done" to `close_all_dialogs()` dismiss texts to handle the error dialog
3. After fix: 4 result i"
tags: [learning, learning, learning-event, fail, unknown]
created: 2026-02-19
severity: fail
video_id: 
affected_tools: []
fix: 1. Updated `generate_product_faithful()` to run `_bg_remove()` before `_product_background()`
2. Added "Done" to `close_all_dialogs()` dismiss texts to handle the error dialog
3. After fix: 4 result i
---

# [FAIL] unknown: Product Background generation timed out at 43% progress. A d

## Symptom

Product Background generation timed out at 43% progress. A dialog appeared: "Background is NOT empty. The background must be empty."

## Root Cause

Product Background does NOT handle BG removal internally (contrary to initial assumption from Dzine marketing). It requires the image to already have a transparent/empty background before it will gene

## Fix Applied

1. Updated `generate_product_faithful()` to run `_bg_remove()` before `_product_background()`
2. Added "Done" to `close_all_dialogs()` dismiss texts to handle the error dialog
3. After fix: 4 result i

## Verification

Always run BG Remove before Product Background. Never assume a Dzine tool handles preprocessing internally.
