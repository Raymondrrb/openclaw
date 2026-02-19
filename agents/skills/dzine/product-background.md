---
description: Product Background tool — THE correct tool for product scene variation. Removes BG + generates scene with prompt + adjusts lighting.
tags: [dzine, tool, product-background, scene-variation, critical]
created: 2026-02-19
updated: 2026-02-19
status: proven
credits: 4
---

# Product Background

The Product Background tool is Dzine's dedicated feature for placing products in different scenes/environments. It's located in Image Editor > Product Background (requires scrolling the subtools panel).

## When to Use

- Creating hero, usage, detail, mood variants of the same product
- Placing a product in a living room, studio, kitchen, outdoor scene
- Any time you need the SAME product in DIFFERENT backgrounds
- Batch processing multiple products with consistent treatment

## When NOT to Use

- Pixel-perfect accuracy for transparent/glass products (AI can blur fine edges)
- When you need to change the product angle/pose (use [[img2img-workflow]] instead)
- Simple aspect ratio changes (use [[generative-expand]] instead)

## How It Works

1. Upload product image → Dzine auto-detects and isolates product
2. Browse template categories OR write custom prompt for background
3. AI removes background, composites product, adjusts lighting/shadows
4. Download result

## Automation Code

```python
# Scroll Image Editor panel to reveal Product Background
page.evaluate("""() => {
    var panel = document.querySelector('.subtools');
    if (panel) { panel.scrollTop = panel.scrollHeight; return true; }
    return false;
}""")
page.wait_for_timeout(500)

# Click Background subtool
page.evaluate("""() => {
    for (const el of document.querySelectorAll('.subtool-item')) {
        var text = (el.innerText || '').trim();
        if (text === 'Background') { el.click(); return true; }
    }
    return false;
}""")
```

Position: `(92, 877)` — CSS class: `subtool-item`
Panel reference: `agents/dzine_playbook.md` line 1635

## Prompt Strategy

Product Background responds well to scene-specific prompts because it's designed for this purpose (unlike [[generative-expand]] which ignores them). Use prompts from [[prompts/hero-shot]], [[prompts/lifestyle-shot]], [[prompts/detail-shot]], [[prompts/mood-shot]].

Key prompt elements that work:

- **Surface/floor material**: "polished concrete floor", "warm oak hardwood"
- **Lighting description**: "afternoon sunlight through windows", "three-point studio lighting"
- **Environment context**: "modern Scandinavian living room", "professional dark studio"
- **Camera angle hint**: "eye-level perspective", "low angle 15 degrees"
- **Atmosphere**: "cozy and inviting", "dramatic and cinematic"

## Relationship to Other Tools

- Prerequisite: None (handles BG removal internally)
- Alternative: [[bg-remove]] + [[generative-expand]] (worse — expand ignores prompts)
- Alternative: [[img2img-workflow]] with faithful reproduction as reference (changes product too)
- Complementary: [[local-edit]] for post-processing artifacts
