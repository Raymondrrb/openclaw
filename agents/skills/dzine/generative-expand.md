---
description: Generative Expand — canvas extension tool. Does NOT create scenes. Prompt influence is minimal. Use only for aspect ratio changes.
tags: [dzine, tool, generative-expand, limitation]
created: 2026-02-19
updated: 2026-02-19
status: limited
credits: 8
---

# Generative Expand

Extends image boundaries by AI-filling the expanded area. Located in Image Editor > Expand.

## CRITICAL LIMITATION

Generative Expand does NOT place products in scenes. It only extends the canvas uniformly, filling with a continuation of the existing edges. **Prompts have minimal to no effect on the output.**

Evidence: See [[../learnings/2026-02-19-identical-images]] — 18 images generated with 5 different backdrop prompts all produced nearly identical plain backgrounds.

## When to Use

- Changing aspect ratio (e.g., square product photo → 16:9 for video)
- Adding margin/breathing room around a product
- Extending a background that already has the desired scene

## When NOT to Use

- Creating different scenes/environments for the same product → use [[product-background]]
- Any case where the prompt describes a specific scene → use [[product-background]] or [[img2img-workflow]]
- When visual variety between variants is needed

## How It Works

1. Open Image Editor > Expand
2. Select aspect ratio preset (16:9, 4:3, 1:1, etc.)
3. Optionally enter prompt (mostly ignored)
4. Drag canvas edges to define expansion area
5. Click Generate (8 credits)
6. Returns 4 results — all similar because prompt is ignored

## Automation

Already automated in `tools/lib/dzine_browser.py` function `_generative_expand()` (line 1979).
Uses shared session via [[shared-session]].

Position: `(92, 401)` — CSS class: `collapse-option`

## Cost Warning

At 8 credits per generation, this is 2x more expensive than Product Background (4 credits) while producing worse results for scene variation. Only use when you specifically need canvas extension.
