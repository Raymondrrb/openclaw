---
description: Product Background tool — THE correct tool for product scene variation. Requires BG Remove first, then generates scene with prompt + adjusts lighting.
tags: [dzine, tool, product-background, scene-variation, critical]
created: 2026-02-19
updated: 2026-02-19
status: proven
credits: 8
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

1. **PREREQUISITE**: Run BG Remove first — Product Background shows "Background is NOT empty" error otherwise
2. Navigate to Image Editor > Background subtool
3. Click **Prompt** tab (class `.pro-tab`, text "Prompt")
4. Click **Manual Prompt** toggle (class `.to-manual-prompt`) to switch to freeform textarea
5. Fill textarea (placeholder: "Descreva tanto o produto quanto o ambiente...")
6. Click **Generate** button (class `.generative`, costs 8 credits)
7. Wait for 4 result images (typically 15-30s)

## Panel Structure (discovered 2026-02-19)

```
Panel class: c-gen-config show float-gen-btn float-pro-img-gen-btn
├── Source Preview (product image)
├── Tabs: Template | Prompt | Image  (class: .pro-tab)
├── [Prompt tab]
│   ├── Toggle: Manual Prompt / Assisted Prompt (class: .to-manual-prompt)
│   ├── Textarea (placeholder: "Descreva tanto o produto quanto o ambiente...")
│   └── Generate button (class: .generative, text: "Generate" + credit badge)
└── [Template tab]
    └── Preset backgrounds: White, +Shadow, Black, Green, etc.
```

## Automation Code

```python
# 1. BG Remove first (REQUIRED)
bg_time = _bg_remove(page)

# 2. Open Image Editor > Background
page.evaluate("""() => {
    var panel = document.querySelector('.subtools');
    if (panel) panel.scrollTop = panel.scrollHeight;
}""")
# Click Background subtool (.subtool-item text "Background")

# 3. Click Prompt tab
page.evaluate("""() => {
    for (var tab of document.querySelectorAll('.pro-tab'))
        if (tab.innerText.trim() === 'Prompt') tab.click();
}""")

# 4. Click Manual Prompt toggle
document.querySelector('.to-manual-prompt').click()

# 5. Fill textarea (use nativeTextAreaValueSetter for React compat)
# 6. Click .generative button (ignore disabled attr — React lag)
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

- **Prerequisite**: [[bg-remove]] — MUST run before Product Background
- Alternative: [[bg-remove]] + [[generative-expand]] (worse — expand ignores prompts)
- Alternative: [[img2img-workflow]] with faithful reproduction as reference (changes product too)
- Complementary: [[local-edit]] for post-processing artifacts

## Critical Rules

- **Never change product color** — if the Amazon listing shows white, the output must be white. Aesthetic only.
- **Verify BG Remove didn't erase the product** — if product is clipped/partially erased, use tighter crop or alternate reference image. Fix immediately.
- **Vary prompts across videos** — rotate lighting, angles, environments to avoid same-looking content across different videos.
- **Authenticity** — no over-stylization. The product must look like what the customer receives.
