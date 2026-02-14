# Seedance Product B-Roll — High-Fidelity Workflow

Last updated: 2026-02-13

---

## Credit Reality Check

**Current balance: ~8.850 video credits**

| Model | Credits/clip | Max clips possible |
|-------|-------------|-------------------|
| Wan 2.1 | 6 | 1 clip (2.850 remaining) |
| Seedance Pro Fast | 7-35 | 1 clip at minimum (1.850 remaining) |
| Wan 2.5 | 7-21 | 1 clip at minimum |
| Dzine Video V1 | 10 | 0 (insufficient for full workflow) |
| Seedance 1.5 Pro | 12-56 | 0 |
| Seedance Pro | 25-120 | 0 |

**Bottom line:** With 8.850 credits, you can generate 1 test clip (Wan 2.1 at 6cr or Seedance Pro Fast at 7cr). A full 5-8 clip B-roll package requires **42-280 credits minimum**. Plan purchases accordingly.

**Cost estimate for a full video B-roll set:**

| Strategy | Model | Clips | Total Credits |
|----------|-------|-------|---------------|
| Budget | Wan 2.1 (6cr) | 6 clips | 36 credits |
| Mid-tier | Seedance Pro Fast (7cr) | 6 clips | 42-210 credits |
| Quality | Seedance 1.5 Pro (12cr) | 6 clips | 72-336 credits |
| Premium | Seedance Pro (25cr) | 6 clips | 150-720 credits |

**Recommendation:** Start with 1 test clip on Seedance Pro Fast (7cr) to validate fidelity, then batch-generate remaining clips if results are acceptable.

---

## A) Product Fidelity Pack (PFP)

### Step A1: Collect Reference Images

Download from Amazon listing + manufacturer site:

| # | Angle | Purpose | Priority |
|---|-------|---------|----------|
| 1 | Front hero (main image) | Primary identity anchor | REQUIRED |
| 2 | Back view | Logo/branding verification | REQUIRED |
| 3 | Left profile | Silhouette consistency | REQUIRED |
| 4 | Right profile | Symmetry check | HIGH |
| 5 | Top view | Controls/ports layout | HIGH |
| 6 | 45-degree angle | 3D form verification | HIGH |
| 7 | In-use lifestyle | Scale reference (hands/environment) | MEDIUM |
| 8 | Detail: logo/branding | Exact placement reference | MEDIUM |
| 9 | Detail: buttons/ports | Feature layout anchor | MEDIUM |
| 10 | Detail: texture/material | Material fidelity reference | MEDIUM |
| 11 | Packaging (if relevant) | Color accuracy cross-check | LOW |
| 12 | User review photos | Real-world appearance validation | LOW |

**Minimum viable set: 6 images (front, back, left, 45-degree, top, in-use)**

Save to: `data/videos/{video_id}/product_fidelity/{asin}/`

### Step A2: Product Identity Spec (PIS)

```json
{
  "product_name": "Sony WH-1000XM5",
  "ASIN": "B09XS7JWHH",
  "category": "over-ear headphones",
  "colorways_allowed": ["black", "platinum silver"],
  "identity_anchors": [
    "smooth oval ear cups (no visible hinges)",
    "thin adjustable headband with synthetic leather",
    "SONY logo on left ear cup (silver on black, dark on silver)",
    "single multifunction button + custom button on left cup",
    "USB-C port on bottom of left ear cup",
    "3.5mm jack on bottom of right ear cup"
  ],
  "forbidden_changes": [
    "no folding mechanism (XM5 does NOT fold, unlike XM4)",
    "no visible screws on headband",
    "no colored accents (all monochrome)",
    "no extra buttons or controls"
  ],
  "must_show_details": [
    "smooth seamless ear cup surface",
    "thin headband silhouette",
    "SONY branding (correct position and size)"
  ]
}
```

### Step A3: Realism Strategy Selection

| Strategy | Description | When to Use | Fidelity Risk |
|----------|-------------|-------------|---------------|
| 1 (safest) | Close, stable shots + low motion + strong refs | First attempt, complex products | LOW |
| 2 (balanced) | Medium motion hands + static BG + strong refs | After Strategy 1 validates | MEDIUM |
| 3 (cinematic) | Dynamic camera movement | Only if S1+S2 pass fidelity | HIGH |

**Default: Strategy 1** — start here for every product.

---

## B) Shot List Template (5-8 Clips)

### Standard B-Roll Package (adapt by product category)

| Shot | Type | Duration | Camera | Strategy | Credits (Pro Fast) |
|------|------|----------|--------|----------|-------------------|
| 1 | Hero close-up | 4-5s | Slow push-in | S1 | 7 |
| 2 | Hand pick-up | 3-4s | Static/slight tilt | S2 | 7-15 |
| 3 | Primary use action | 4-5s | Medium shot, stable | S2 | 7-15 |
| 4 | Detail close-up | 3-4s | Macro, minimal motion | S1 | 7 |
| 5 | Environment context | 4-5s | Slow pan across scene | S1 | 7-15 |
| 6 | Reset/outro | 3-4s | Static wide | S1 | 7 |

**Total for 6-clip minimum:** 42-74 credits (Seedance Pro Fast)

### Category-Specific Adaptations

**Electronics (headphones, speakers, mice):**
- Hero: product on dark desk, soft rim light
- Use: wearing/holding near ear/hand
- Detail: button close-up, indicator LED
- Context: desk setup with monitor blurred behind

**Kitchen (blender, coffee maker, utensils):**
- Hero: product on marble/granite counter
- Use: hands operating controls
- Detail: material texture, dials
- Context: kitchen environment, natural light

**Personal Care (shaver, toothbrush, skincare):**
- Hero: product on bathroom shelf
- Use: hand holding near face (avoid actual face)
- Detail: bristles/blades close-up
- Context: clean bathroom, morning light

---

## C) Seedance Prompting Rules

### Prompt Structure (Anti-Drift)

```
[FIDELITY ANCHOR] + [ACTION] + [ENVIRONMENT] + [LIGHTING] + [CAMERA] + [CONSTRAINTS]
```

### Prompt Template

```
Ultra-realistic b-roll video of the EXACT product shown in the reference images
(same shape, same colors, same branding/logo placement, same buttons/ports,
same proportions). {ACTION_DESCRIPTION}. Clean {ENVIRONMENT}, {LIGHTING},
physically accurate shadows, correct scale. Camera: {CAMERA_MOVEMENT}.
Keep the product design identical to references; do not stylize; do not redesign.
```

### Negative Template

```
Do NOT alter product design. No extra buttons. No different logo. No different color.
No fantasy materials. No AI artifacts. No cartoon/anime. No text overlays.
No fake labels. No unrealistic glow. No exaggerated motion blur.
No additional accessories not present in references.
```

### Key Prompting Rules

1. **Always lead with fidelity anchor:** "EXACT product shown in reference images"
2. **Explicitly forbid redesign** in every prompt
3. **Keep backgrounds simple:** plain surfaces, minimal props
4. **Neutral lighting default:** soft daylight / softbox (avoid dramatic unless needed)
5. **Hands must be realistic:** "adult hands, natural grip, correct scale relative to product"
6. **Limit motion complexity:** less motion = less drift
7. **One action per clip:** don't combine pick-up + use + put-down

### Reference Input Strategy (Dzine AI Video)

**Key Frame Mode (cheaper, 6-35 credits):**
- Upload a single high-quality product image as Start Frame
- Write detailed prompt describing the motion/scene
- Best for: static product shots with slow camera motion

**Reference Mode (expensive, 85 credits — avoid until budget allows):**
- Upload multiple reference images
- Use `@Image1` mentions in prompt
- Best for: complex multi-reference scenes
- NOT recommended at current credit level

---

## D) Shot Prompts (Template Per Shot)

### Shot 1: Hero Close-Up

```
Purpose: Establish product identity
Duration: 5s
Aspect: 16:9
Strategy: S1 (safest)
Model: Seedance Pro Fast (7 credits) or Wan 2.1 (6 credits)

Inputs:
- Start Frame: front hero image (angle #1 from PFP)
- Reference video: none

PROMPT:
Ultra-realistic b-roll video of the EXACT product shown in the reference image
(same shape, same colors, same branding/logo placement, same proportions).
Product resting on a clean dark matte surface. Soft studio lighting with gentle
key light from upper left. Very slow push-in zoom, barely perceptible. Shallow
depth of field, product razor-sharp, background softly blurred.
Keep product design identical to reference; do not stylize.

NEGATIVE:
Do NOT alter product design. No extra buttons. No different color. No fantasy
materials. No AI artifacts. No cartoon/anime. No unrealistic glow.

NOTES:
- Use highest-quality product image as start frame
- Minimal camera motion reduces drift risk
- If product shape drifts: switch to completely static shot
```

### Shot 2: Hand Pick-Up

```
Purpose: Human interaction, natural feel
Duration: 4s
Aspect: 16:9
Strategy: S2 (medium)

PROMPT:
Ultra-realistic b-roll of an adult hand naturally picking up the EXACT product
shown in the reference image from a clean wooden desk. Soft natural daylight
from a window on the left. Hand approaches from right side, fingers wrap around
product at correct scale. Smooth, natural motion. Static camera, medium shot.
Product maintains exact shape, color, and branding from reference.

NEGATIVE:
No altered product design. No extra fingers. No incorrect hand proportions.
No cartoon style. No dramatic lighting. No product redesign.

NOTES:
- Hands are high-risk for AI artifacts — validate finger count
- If hand quality is poor: crop tighter to just fingertips touching product
- Product scale must match hand size realistically
```

### Shot 3: Primary Use Action

```
Purpose: Show product being used for its main purpose
Duration: 5s
Aspect: 16:9
Strategy: S2

PROMPT:
Ultra-realistic b-roll of a person naturally using the EXACT product shown in
the reference image. {SPECIFIC_USE_ACTION}. Clean, simple background with
realistic {ENVIRONMENT}. Soft natural lighting, physically accurate shadows.
Medium shot, camera slightly above eye level, minimal movement.
Product maintains exact appearance from reference throughout.

NEGATIVE:
No altered product. No exaggerated effects. No fantasy. No AI artifacts.
No different color or shape. No additional accessories.

NOTES:
- Customize {SPECIFIC_USE_ACTION} per product category
- Keep action simple: one clear motion
- Background should match product category (desk/kitchen/bathroom)
```

### Shot 4: Detail Close-Up

```
Purpose: Highlight key feature/texture
Duration: 3s
Aspect: 16:9
Strategy: S1 (safest)

PROMPT:
Extreme close-up ultra-realistic b-roll of the EXACT product's {KEY_FEATURE}
shown in the reference image. Macro-style framing showing {DETAIL_DESCRIPTION}.
Product fills most of frame. Soft even lighting revealing material texture.
Very slight slow drift to the right. Shallow depth of field.
Exact same materials, colors, and textures as reference.

NEGATIVE:
No altered design details. No different texture. No fantasy materials.
No AI smoothing. No cartoon. No blur on the product itself.

NOTES:
- Use detail close-up image as start frame (angle #8-9 from PFP)
- Minimal motion = safest for preserving fine details
- If texture drifts: try static shot with zero camera motion
```

### Shot 5: Environment Context

```
Purpose: Show product in natural environment
Duration: 4s
Aspect: 16:9
Strategy: S1

PROMPT:
Ultra-realistic establishing shot of the EXACT product shown in reference
sitting naturally in a {ENVIRONMENT}. Product positioned at left third of frame.
{ENVIRONMENT_DETAILS}. Natural ambient lighting from {LIGHT_SOURCE}.
Very slow pan from left to right revealing the scene. Product maintains exact
shape, color, and branding from reference.

NEGATIVE:
No product redesign. No fantasy environment. No dramatic filters.
No AI artifacts. No text overlays.

NOTES:
- Product at rest, no interaction
- Environment should be simple and uncluttered
- Pan should be very slow (reduces artifact risk)
```

### Shot 6: Reset/Outro

```
Purpose: Clean transition shot, product at rest
Duration: 3s
Aspect: 16:9
Strategy: S1

PROMPT:
Ultra-realistic b-roll of the EXACT product from reference placed neatly on a
clean surface. Product centered in frame, slightly angled. Soft diffused
lighting, minimal shadows. Completely static camera. Clean, premium feel.
Product identical to reference in every detail.

NEGATIVE:
No altered design. No movement. No artifacts. No text. No additional objects.

NOTES:
- Static shot = zero drift risk
- Good for opening/closing transitions
- Can use as safety shot if other clips have fidelity issues
```

---

## E) Fidelity Validation Checklist

After each generated clip, validate ALL items:

| # | Check | Pass/Fail | Action if Fail |
|---|-------|-----------|----------------|
| 1 | Silhouette match | | Regenerate with closer/static shot |
| 2 | Color/material match | | Add "exact same color" emphasis in prompt |
| 3 | Logo placement match | | Use close-up reference as start frame |
| 4 | Feature layout (buttons/ports) | | Switch to Strategy 1, reduce motion |
| 5 | Scale realism (hands vs product) | | Adjust prompt: "product is {X}cm tall" |
| 6 | Artifact check (warping/melting) | | Reduce motion, shorter duration |
| 7 | Hand realism (if present) | | Remove hands, use product-only shot |
| 8 | Background consistency | | Simplify background description |

### Failure Escalation

1. **1 check fails:** Regenerate same prompt (AI is non-deterministic)
2. **2 checks fail:** Simplify prompt, reduce motion, add more constraints
3. **3+ checks fail:** Downgrade to Strategy 1 (static shots only)
4. **Silhouette fails repeatedly:** Product may be too complex for video AI — use static images with slow Ken Burns zoom in DaVinci Resolve instead

---

## F) Dzine AI Video Step-by-Step (Playwright)

### Generate a Single B-Roll Clip

```python
# 1. Open AI Video panel
page.mouse.click(40, 361)
page.wait_for_timeout(2000)

# 2. Select "Key Frame" mode (default)
# Already selected by default

# 3. Upload start frame (product hero image)
upload_btn = page.locator('button.pick-image.has-guide').first
with page.expect_file_chooser(timeout=5000) as fc_info:
    upload_btn.click()
fc = fc_info.value
fc.set_files(str(start_frame_path))
page.wait_for_timeout(3000)

# 4. Fill prompt
prompt_area = page.locator('.c-gen-config.show textarea').first
prompt_area.click()
page.keyboard.press('Meta+a')
page.keyboard.type(shot_prompt, delay=3)

# 5. Select model (click model selector)
page.evaluate("""() => {
    var panel = document.querySelector('.c-gen-config.show');
    var sel = panel.querySelector('.custom-selector-wrapper');
    if (sel) sel.click();
}""")
page.wait_for_timeout(2000)
# Select cheapest viable model
page.evaluate("""() => {
    var popup = document.querySelector('.selector-panel');
    if (!popup) return;
    var items = popup.querySelectorAll('*');
    for (var item of items) {
        if ((item.innerText || '').includes('Seedance Pro Fast')) {
            item.click(); return 'selected';
        }
    }
}""")
page.wait_for_timeout(1000)

# 6. Generate (check credits first!)
gen_btn = page.locator('.c-gen-config.show .generative.ready').first
credit_text = gen_btn.inner_text()
print(f"Generation cost: {credit_text}")
# Only click if you're sure about credit spend
gen_btn.click()

# 7. Wait for generation (video takes 30-120s)
page.wait_for_timeout(5000)
# Poll for completion
import time
start = time.time()
while time.time() - start < 180:
    results = page.locator('.result-item.image-to-video-result').count()
    if results > 0:
        break
    page.wait_for_timeout(5000)
```

### Download Generated Video

```python
# Click download on the video result
page.evaluate("""() => {
    var dlBtn = document.querySelector('.result-item.image-to-video-result button:has-text("Download")');
    if (dlBtn) dlBtn.click();
}""")
```

---

## G) Credit-Conscious Workflow

### Phase 1: Validate (1 clip, 6-7 credits)
1. Prepare PFP (6+ images)
2. Write PIS
3. Generate Shot 1 (hero close-up) with cheapest model
4. Run fidelity checklist
5. If PASS: proceed to Phase 2
6. If FAIL: adjust strategy, DO NOT generate more until fixed

### Phase 2: Batch Generate (needs credit top-up)
1. Buy credits based on plan:
   - 6 clips x Seedance Pro Fast (7cr) = 42 credits minimum
   - 6 clips x Wan 2.1 (6cr) = 36 credits minimum
2. Generate remaining 5 shots
3. Validate each clip
4. Re-generate failed clips

### Phase 3: Post-Production
1. Download all clips
2. Import into DaVinci Resolve
3. Color grade for consistency
4. Trim/sequence clips
5. Add to timeline alongside voiceover

---

## H) Product Categories — Shot Adaptations

### Headphones/Earbuds
- Hero: on dark surface, slight rim light on ear cups
- Use: person wearing, head slightly turned
- Detail: close-up of ear cup cushion, buttons
- Context: desk with monitor, work-from-home setup

### Kitchen Appliances
- Hero: on marble counter, kitchen background blurred
- Use: hand pressing start button / pouring liquid
- Detail: control dial close-up, material texture
- Context: bright kitchen, morning light

### Smart Home / Tech
- Hero: on shelf/nightstand, ambient glow
- Use: hand interacting with touch surface
- Detail: LED indicators, ports
- Context: living room, evening ambiance

### Personal Care
- Hero: on bathroom shelf, clean white
- Use: hand holding near face (avoid generating full face)
- Detail: bristles/blade/nozzle close-up
- Context: clean bathroom, soft morning light

### Outdoor/Sports
- Hero: on natural surface (wood, stone)
- Use: hand gripping during activity
- Detail: clip/strap/button mechanism
- Context: outdoor setting, golden hour

---

## Sources

- Dzine AI Video model catalog (Phase 150 exploration)
- Dzine canvas UI exploration (Phases 140-157)
- [Seedance 2.0 Guide](https://www.dzine.ai/blog/seedance-2-0-guide/)
- DaVinci Resolve automation guide (local)
