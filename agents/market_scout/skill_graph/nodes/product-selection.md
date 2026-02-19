---
id: product-selection
title: Product Selection Logic
description: Enforces same-category Top 5 selection with quality filters and anti-repeat windows.
tags: [products, ranking, amazon, top5]
links: ["[[evidence-claims]]", "[[gate1-review]]", "[[observability-receipts]]"]
---

# Product Selection Logic

Use a single category per run and rank five competitors in that same category.

## Hard Filters

- Price floor and ceiling from run policy.
- Minimum rating and review thresholds.
- Exclude out-of-stock and unavailable listings.
- Exclude ASINs used in the last configured day window.

Export structured outputs first, then write narration from those outputs.
