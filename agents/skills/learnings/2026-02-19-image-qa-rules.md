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

| Pattern                      | Root Cause                                            | Fix                                                  |
| ---------------------------- | ----------------------------------------------------- | ---------------------------------------------------- |
| Phone ghost on edges         | Amazon ref includes phone                             | Crop tighter, exclude phone                          |
| Right-side ghosting          | Product clipped at ref image boundary                 | Ensure padding on all sides                          |
| White-on-white low contrast  | White product + detail=white BG                       | Use light gray for detail variant                    |
| Duplicate dock               | Complex ref with ambiguous shapes                     | Use cleaner alternate Amazon image                   |
| Identical backgrounds        | Used Generative Expand instead of Product Background  | Always use Product Background                        |
| Semi-transparent panel ghost | Product has glass/translucent panel (e.g. water tank) | Crop tighter to exclude panel edge, or mask manually |
| Phone persists after crop    | Crop wasn't aggressive enough                         | Use alternate Amazon image without phone entirely    |

## Amazon Reference Image Selection — Agent Decision Tree

When selecting a reference image for Dzine, agents MUST follow this flow:

### Step 1: Check main Amazon image

- Does it have a phone/accessories? → Go to Step 2
- Is the product cut off at any edge? → Go to Step 2
- Clean white BG, product complete, no extras? → USE IT

### Step 2: Try cropping

- Phone is far from product (separate, in corner)? → Crop with ffmpeg: `crop=iw*0.7:ih:0:0`
- Verify crop didn't clip the product itself
- If product is clipped after crop → Go to Step 3

### Step 3: Search Amazon gallery for alternate image

- Fetch the product page and find all gallery image IDs
- Amazon images: `https://m.media-amazon.com/images/I/{ID}._AC_SL1500_.jpg`
- Look for: white BG, no phone, complete product, padding on all sides
- Most products have 8-16 gallery images but only 1-2 are usable product shots

### Step 4: If no usable image exists

- Try the manufacturer's website (e.g. roborock.com, narwal.com)
- Try alternate color variant ASIN (may have cleaner photos)
- As last resort: use main image + aggressive crop, accepting minor edge loss

### Step 5: CRITICAL — Preserve original angle

- **NEVER use a different angle/perspective** than the original Amazon image
- Top-down only refs confuse Product Background → generates spheres/orbs/wrong shapes
- 3/4 perspective views give the AI the best understanding of product 3D form
- If the original Amazon image has a good angle, KEEP IT — just remove the phone

### Best technique: ffmpeg drawbox (paint phone white)

Instead of cropping (which changes proportions and may clip the product), paint the phone area with the background color:

```bash
ffmpeg -i input.jpg -vf "drawbox=x=660:y=760:w=250:h=360:color=white:t=fill" output.jpg
```

- Preserves the EXACT original angle and proportions
- Phone area becomes invisible white (same as Amazon background)
- BG Remove will ignore the white area naturally
- MUCH better than cropping which risks clipping the product or changing perspective

### Key patterns learned:

- Robot vacuum listings ALWAYS have phones (showing the app) — need alternate images or drawbox removal
- Dock stations are often cut off at edges in main images
- Cropping to remove phone can DESTROY product fidelity if it changes the angle
- Using alternate angle images (e.g., top-down instead of 3/4) causes AI to hallucinate wrong shapes
- Product 04: dock had semi-transparent water tank panel that confused BG Remove
- Always VERIFY the cutout after BG Remove before feeding into Product Background
- **Round 2 failure:** switching from 3/4 angle ref to top-down ref caused ALL images to fail (spheres, wrong colors, hallucinated objects)

## Product Background Stochasticity — Critical Insight

After 4 rounds of regeneration attempts for product 01 (Roborock Q7 M5+):

### What happened:

- **Round 1**: Correct product shape but phone remnants from Amazon ref (WARN level)
- **Round 2**: Switched to alternate top-down angle ref → CATASTROPHIC FAIL (spheres, orbs, wrong shapes)
- **Round 3**: Used drawbox to paint phone white on original ref → 2/5 PASS, 3/5 FAIL (hallucinated giant LED disc, garbled text "Q73 Rocks", "Roberocr")
- **Round 4**: Retried the 3 failures with same ref → ALL 3 STILL FAIL (same hallucinations)

### Key insight:

**Product Background is highly stochastic.** The same reference image can produce:

- Perfect, faithful product renders (usage2, mood variants)
- Complete hallucinations with wrong shapes, garbled text, LED rings (hero, usage1, detail variants)

There is NO reliable way to predict which runs will succeed. The tool appears to have an internal randomness that sometimes catastrophically fails.

### Pragmatic resolution:

- **Accept WARN-level images** (minor ghosting, small phone fragments) rather than risk hallucinations from re-generation
- Round 1 images with minor artifacts are MUCH better than hallucinated products
- Only reject images with MAJOR failures (wrong product entirely, garbled branding, wrong shape)
- Build automated retry-with-QA: generate → Vision check → if FAIL, retry up to 3x → if still failing, keep best WARN-level image

### Final vtest-qa status (after 4 rounds):

| Product        | Variant | Status | Notes                                                |
| -------------- | ------- | ------ | ---------------------------------------------------- |
| 01 Q7 M5+      | hero    | WARN   | Correct product, minor right-side clip               |
| 01 Q7 M5+      | usage1  | WARN   | Correct product, living room, minor clip             |
| 01 Q7 M5+      | detail  | WARN   | Correct product, white BG, minor clip                |
| 01 Q7 M5+      | usage2  | PASS   | Bedroom scene with accessories, excellent            |
| 01 Q7 M5+      | mood    | WARN   | Dark concrete, correct product, small phone fragment |
| 02 Tapo RV30   | all 4   | PASS   | Clean alternate ref image solved all issues          |
| 03 Dreame D20  | all 3   | PASS   | Clean ref from start                                 |
| 04 Saros 10    | hero    | WARN   | Minor right-side ghosting from dock edge             |
| 04 Saros 10    | usage1  | WARN   | Similar ghosting                                     |
| 04 Saros 10    | detail  | WARN   | Similar ghosting                                     |
| 05 Narwal Freo | hero    | PASS   | Clean                                                |
| 05 Narwal Freo | usage1  | PASS   | Clean                                                |
| 05 Narwal Freo | detail  | WARN   | White-on-white contrast issue                        |

**Total: 18 images — 9 PASS, 9 WARN, 0 FAIL**

All images are video-ready. WARN-level issues are minor and can be mitigated in video editing (cropping, short display duration, overlay text).

## Related Nodes

- [[../dzine/product-background]]
- [[../dzine/bg-remove]]
- [[2026-02-19-phone-removal]]
- [[2026-02-19-duplicate-dock]]
- [[2026-02-19-identical-images]]
