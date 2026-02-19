---
description: "ASIN B0F8HM4PYL (Narwal Freo Pro) was actually replacement accessories at $26.59 instead of the vacuum at $400+. New validation catches price <30% of category median."
tags: [learning, learning, research, data-quality, critical]
created: 2026-02-19
severity: high
video_id: v038
affected_tools: [researcher, pipeline]
fix: Added price anomaly detection and accessory keyword filter to validate_products()
---

# v038 ASIN accessories detected by price anomaly

## What happened

Product rank 5 in v038 (Narwal Freo Pro, ASIN B0F8HM4PYL) was actually a 16-piece replacement accessories kit priced at $26.59, not the actual robot vacuum ($400+).

## Root cause

No price validation existed. The researcher accepted the ASIN without checking if the price was reasonable for the category.

## Fix applied

- Added price anomaly detection: flag products with price <30% of category median
- Added accessory keyword filter: detect "replacement", "kit", "pack of", etc. in product names
- Added duplicate evidence detection: flag when same text is used for multiple products

## Prevention

- validate_products() now runs these checks automatically
- Researcher SOUL updated with concrete validation methodology
