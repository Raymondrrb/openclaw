---
description: MOC for pipeline architecture — asset generation, validation, orchestration.
tags: [moc, pipeline, architecture]
created: 2026-02-19
updated: 2026-02-19
---

# Pipeline Skills

How the RayviewsLab video production pipeline works.

## Asset Generation

- [[product-faithful]] — Current workflow for product images. Uses BG Remove + Generative Expand (NEEDS MIGRATION to Product Background).
- [[asset-quality-gate]] — How generated assets are validated (size, format, fidelity).

## Runtime Reliability

- [[openclaw-stability-guardrails]] — Prevent and recover OpenClaw process storms on Mac.
- [[claude-code-execution-contract]] — Prompt contract to keep Claude Code within safe execution patterns.
- [[telegram-approval-matrix]] — Low-noise Telegram approvals by stage owner (niche/products/assets/gates).

## Key Architecture

- Pipeline entry: `tools/pipeline.py` function `cmd_assets()`
- Backdrop prompts: defined in `_BACKDROP_PROMPTS` dict (line 1187)
- Routing decision: `use_faithful` flag (line 1208)
- Generation: calls `generate_product_faithful()` or `generate_image()`

## Reference Images

- Amazon images: `artifacts/videos/{video_id}/assets/amazon/`
- Cropped refs (phone-free): `artifacts/videos/{video_id}/assets/amazon/cropped/`
- Generated products: `artifacts/videos/{video_id}/assets/dzine/products/`

## Pending Improvements

1. Replace Generative Expand with [[../dzine/product-background]] for scene variation
2. Implement best-of-4 selection (currently takes first result)
3. Two-step workflow: Product Background → Img2Img for creative variants
4. Auto-improvement loop to update prompts based on results
5. Add preflight check in orchestrator to run process pressure check before ChatGPT UI automation
