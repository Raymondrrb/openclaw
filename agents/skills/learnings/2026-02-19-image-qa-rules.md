---
description: Image QA rules learned from first Product Background batch. Check BEFORE every generation run.
tags: [learning, dzine, image-qa, quality, critical]
created: 2026-02-19
updated: 2026-02-19
severity: high
status: active
---

# 2026-02-19 — Image QA Rules

## Mandatory Pre-Generation Checks

Before generating product images, the agent MUST verify:

### Reference Image Quality

1. **No phone in frame** — if Amazon ref has phone, crop tighter or find alternate photo. BG Remove treats phones as foreground and leaves ghost artifacts.
2. **Clean edges on all sides** — product must have padding on all 4 sides. If the product is clipped at the image boundary, BG Remove creates ghosting/transparency on that edge.
3. **No ambiguous objects** — extra docks, cables, accessories that could confuse the AI. Crop to just the product.
4. **Product on simple background** — white/solid backgrounds BG-remove best. Complex backgrounds create artifacts.

### Post-Generation Checks (per image)

1. **Product intact** — no clipping, no erasure, no missing parts
2. **Color preserved** — compare against Amazon ref. NEVER change product color. If Amazon shows white, output must be white.
3. **No phone fragments** — scan edges for rectangular shapes, especially right side
4. **No ghosting** — look for smoky/hazy transparency artifacts on product edges, especially right side
5. **Background appropriate** — professional, matches prompt (dark studio, living room, kitchen, etc.)
6. **White-on-white check** — white products on white backgrounds have poor contrast. Use light gray or colored background instead for detail variant.
7. **File size sanity** — very small files (<80KB) may indicate blank/failed generation

### Video-Ready Threshold

- Score >= 7/10 on all checks above
- No visible phone fragments (instant fail)
- No prominent ghosting (instant fail on dark backgrounds)
- Product color matches Amazon listing exactly

## Known Failure Patterns

| Pattern                     | Root Cause                                           | Fix                                |
| --------------------------- | ---------------------------------------------------- | ---------------------------------- |
| Phone ghost on edges        | Amazon ref includes phone                            | Crop tighter, exclude phone        |
| Right-side ghosting         | Product clipped at ref image boundary                | Ensure padding on all sides        |
| White-on-white low contrast | White product + detail=white BG                      | Use light gray for detail variant  |
| Duplicate dock              | Complex ref with ambiguous shapes                    | Use cleaner alternate Amazon image |
| Identical backgrounds       | Used Generative Expand instead of Product Background | Always use Product Background      |

## Related Nodes

- [[../dzine/product-background]]
- [[../dzine/bg-remove]]
- [[2026-02-19-phone-removal]]
- [[2026-02-19-duplicate-dock]]
- [[2026-02-19-identical-images]]
