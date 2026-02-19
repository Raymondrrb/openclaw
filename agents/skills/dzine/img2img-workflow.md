---
description: Img2Img workflow — transforms entire image including product. Good for style transfer and scene variations with acceptable product drift.
tags: [dzine, tool, img2img, style-transfer]
created: 2026-02-19
updated: 2026-02-19
status: proven
credits: 20
---

# Img2Img Workflow

Transforms an existing image using AI while following the layout structure of the input. The product WILL be modified — fidelity depends on `structure_match` setting.

## When to Use

- Scene variations where some product drift is acceptable
- Style transfer (e.g., sketch → photo, day → night)
- When you have a faithful reproduction from [[product-background]] and want creative variants
- Two-step workflow: Product Background (faithful) → Img2Img (creative variation)

## When NOT to Use

- When pixel-perfect product preservation is required → use [[product-background]]
- When you only need a background change → use [[product-background]] (cheaper, 4 vs 20 credits)

## Key Parameters

- **Structure Match**: 0-1 slider. Higher = more faithful to input layout. For products: 0.7-0.9
- **Style Intensity**: 0-1 slider. Higher = more style deviation
- **Negative Prompt**: Available in Advanced section (1800 chars). Use to exclude unwanted elements
- **Model**: See [[model-selection]] — Nano Banana Pro or Realistic Product recommended

## Prompt Strategy for Products

Img2Img prompts should describe the FULL scene (product + environment) because the model transforms everything:

```
Professional product photography of a robot vacuum cleaner on warm oak hardwood floor.
Modern living room with beige sofa in soft-focus background, indoor plants.
Natural afternoon sunlight from large windows, warm golden tones.
Shallow depth of field, product sharp, background soft bokeh.
```

Include "product unmodified, accurate proportions" to reduce drift.
See [[../prompts/_index]] for variant-specific templates.

## Automation

Automated in `tools/lib/dzine_browser.py`:

- `_generate_img2img()` (line 901) — low-level
- `generate_img2img_variant()` (line 1493) — high-level API
- `_activate_img2img_panel()` (line 866) — panel toggle

## Two-Step Workflow (Recommended for Best Results)

1. **Step 1**: Use [[product-background]] to create a faithful product-in-scene image
2. **Step 2**: Use Img2Img on the Step 1 result with creative prompt variations
3. This gives scene variety WHILE starting from a faithful base

This approach was suggested by the user but not yet implemented in the pipeline.
