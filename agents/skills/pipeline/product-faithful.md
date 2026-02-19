---
description: Product-faithful asset generation workflow. Currently BG Remove + Expand (broken for variety). Migrating to Product Background.
tags: [pipeline, product-faithful, workflow, migration]
created: 2026-02-19
updated: 2026-02-19
status: needs-migration
---

# Product Faithful Pipeline

Generates product images that preserve the real product appearance while placing it in different scenes.

## Current Workflow (BROKEN for variety)

1. Upload Amazon reference image
2. BG Remove — isolate product
3. Generative Expand — extend canvas with "backdrop prompt"
4. Download first result

**Problem**: Generative Expand ignores backdrop prompts. All variants look identical. See [[../learnings/2026-02-19-identical-images]].

## Target Workflow (TO IMPLEMENT)

1. Upload Amazon reference image
2. Open Image Editor > Product Background (scroll down in subtools)
3. Enter variant-specific prompt from [[../prompts/_index]]
4. Generate — Product Background respects scene prompts
5. Compare 4 results, select best match
6. Download best result

## Code Locations

- Pipeline routing: `tools/pipeline.py` line 1208 (`use_faithful` flag)
- Current implementation: `tools/lib/dzine_browser.py` line 2137 (`generate_product_faithful`)
- Backdrop prompts: `tools/pipeline.py` line 1187 (`_BACKDROP_PROMPTS`)
- Prompt templates: [[../prompts/hero-shot]], [[../prompts/lifestyle-shot]], etc.

## Migration Checklist

- [ ] Add `_product_background()` function to dzine_browser.py
- [ ] Update `generate_product_faithful()` to use Product Background instead of Expand
- [ ] Use variant-specific prompts from skill graph instead of generic backdrop prompts
- [ ] Implement best-of-4 selection (SSIM comparison with reference)
- [ ] Record generation results in [[../learnings/_index]] for auto-improvement
