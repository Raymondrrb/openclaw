---
description: MOC for all Dzine platform knowledge — tools, models, workflows.
tags: [moc, dzine, platform]
created: 2026-02-19
updated: 2026-02-19
---

# Dzine Platform Skills

Everything about Dzine.ai for product photography and video asset generation.

## Tool Selection (which tool for which job)

The single most important decision is tool selection. Wrong tool = wasted credits + identical outputs.

- [[product-background]] — THE tool for placing products in different scenes. Removes BG, generates scene with prompt, adjusts lighting. **Use this for hero/usage/mood variants.**
- [[generative-expand]] — Only extends canvas boundaries. Does NOT create scenes. Prompt influence is minimal. **Use only for aspect ratio changes.**
- [[img2img-workflow]] — Transforms entire image including product. Good for style transfer. **Use when you have a faithful reproduction and want a scene variation with acceptable product drift.**
- [[bg-remove]] — Isolates product from background. Prerequisite for [[product-background]] and [[generative-expand]]. Treats phones/accessories as foreground — crop them from reference first.
- [[local-edit]] — Targeted inpainting. Mask an area, describe what to fill. Good for removing artifacts or adding specific elements.
- [[insert-object]] — Places a reference object into a masked area. 150 char prompt limit. Good for compositing product into an existing scene.

## Model Selection

- [[model-selection]] — Which AI model for which asset type. Nano Banana Pro wins 4/7 categories. Realistic Product for faithful studio shots.

## Automation

- [[shared-session]] — Playwright shared session pattern to avoid "Sync API inside asyncio loop" crash
- [[dialog-handling]] — Tutorial/promo popup handling (close_all_dialogs)

## Failures & Recovery

- [[dzine/failures/_index]] — All documented failures with root cause and fix

## Reference

For pixel-perfect coordinates: `agents/dzine_playbook.md` lines 1480-1660
For sidebar positions: `agents/dzine_ui_map.md`
