---
description: Insert Object workflow for compositing a referenced product into a specific masked area.
tags: [dzine, insert-object, compositing]
created: 2026-02-19
updated: 2026-02-19
status: provisional
---

# Insert Object

Insert Object is for controlled compositing when you already have a target scene and need to place the product in one region.

## Best Use Cases

- Place the advertised product into a prebuilt lifestyle background
- Build variant scenes while preserving product identity
- Correct layouts where automatic placement failed

## Constraints

- Prompt budget is short; be direct.
- Mask quality matters more than prompt length.

## Minimal Prompt Formula

`Place product naturally on [surface], correct perspective, realistic shadow, match scene lighting.`

## Quality Checks

1. Product scale matches nearby objects.
2. Contact shadow exists and follows light direction.
3. No halo/cutout edge around inserted object.

If checks fail twice, fallback to [[product-background]] with a stronger scene prompt.
