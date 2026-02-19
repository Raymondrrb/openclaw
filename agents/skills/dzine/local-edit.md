---
description: Local Edit workflow for precise inpainting fixes after generation.
tags: [dzine, local-edit, inpainting, cleanup]
created: 2026-02-19
updated: 2026-02-19
status: proven
---

# Local Edit

Use Local Edit when only a small region is wrong and the rest of the image is good.

## When to Use

- Remove artifacts (extra objects, broken edges, phantom accessories)
- Fix brand-dangerous mistakes before publishing
- Clean up outputs from [[product-background]] or [[img2img-workflow]]

## When NOT to Use

- Full scene restyling (use [[product-background]])
- Product angle or pose change (regenerate instead)

## Practical Workflow

1. Draw a tight mask around only the broken region.
2. Prompt with exact replacement intent.
3. Keep product identity constraints explicit.
4. Re-run once if blend edges look synthetic.

## Prompt Pattern

`Replace masked area with [specific object/texture], keep lighting direction consistent, preserve product shape and branding, photorealistic.`

## Failure Signals

- New artifacts outside mask
- Product logo/text gets distorted
- Lighting mismatch between edited patch and global scene

If any signal appears, rollback and regenerate from previous step rather than stacking edits.
