---
description: "No price validation existed. The researcher accepted the ASIN without checking if the price was reasonable for the category. → - Added price anomaly detection: flag products with price <30% of category median
- Added accessory keyword filter: detect "replacement", "kit", "pack of", etc. in product names
- Added duplicate evid"
tags: [learning, learning, learning-event, fail, unknown]
created: 2026-02-19
severity: fail
video_id: v038
affected_tools: []
fix: - Added price anomaly detection: flag products with price <30% of category median
- Added accessory keyword filter: detect "replacement", "kit", "pack of", etc. in product names
- Added duplicate evid
---

# [FAIL] unknown: v038 ASIN accessories detected by price anomaly

## Symptom

v038 ASIN accessories detected by price anomaly

## Root Cause

No price validation existed. The researcher accepted the ASIN without checking if the price was reasonable for the category.

## Fix Applied

- Added price anomaly detection: flag products with price <30% of category median
- Added accessory keyword filter: detect "replacement", "kit", "pack of", etc. in product names
- Added duplicate evid
