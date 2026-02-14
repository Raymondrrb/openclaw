# Dzine Image Generation -- Standard Operating Procedures

Strict, numbered checklists for automated Dzine image generation via Playwright.
Each SOP is self-contained. The operator MUST follow every step in order; do NOT skip steps.

Canvas URL: `https://www.dzine.ai/canvas?id=19797967`
Viewport: `1440x900` (mandatory -- sidebar positions break at other sizes)
Browser: OpenClaw Brave via CDP port 18800

---

## SOP 1: THUMBNAIL

Mode: Txt2Img | Ratio: 16:9 (canvas) | Model: Seedream 4.5 (primary) or Nano Banana Pro (fallback)
Product showcase, no Ray. One per video.
Model selection: use `recommended_model("thumbnail")` from `dzine_schema.py`.

### Preconditions

- [ ] Brave browser running with CDP on port 18800
- [ ] Logged in as Ramon Reis (Master plan)
- [ ] Canvas page loaded (`dzine.ai/canvas?id=19797967`)
- [ ] Viewport set to 1440x900 via `page.set_viewport_size({"width": 1440, "height": 900})`

### Steps

1. **Close dialogs** -- call `close_all_dialogs(page)`. Dismiss "Not now", "Close", "Got it", "Skip", "Later" buttons. Loop up to 8 rounds.
2. **Exit any active tool mode** -- call `_exit_tool_mode(page)`. Handles Expression Edit back arrow, AI Eraser Exit button, and sidebar state reset.
3. **Activate Txt2Img panel** -- click Img2Img sidebar icon at `(40, 252)`, wait 500ms, then click Txt2Img sidebar icon at `(40, 197)`, wait 1500ms. Verify panel header contains "Text to Image" via `.gen-config-header`. If not active, double-click Txt2Img icon as fallback.
4. **Select model** -- click `button.style` to open style picker. Find `.style-name` element matching "Seedream 4.5" (preferred) or "Nano Banana Pro" (fallback). Click the parent card. Press Escape to close picker. Wait 1000ms. Use `recommended_model("thumbnail")` for the model name.
5. **Fill prompt** -- click at position `(101, 175)` to focus the Txt2Img textarea. Press `Cmd+A` to select all. Type the thumbnail prompt using `PROMPT_TEMPLATES["thumbnail"]` from `dzine_schema.py`, formatted with `{product_name}`. Max 1800 chars. Delay: 3ms per keystroke.
6. **Set aspect ratio** -- click `.c-aspect-ratio .item.canvas` (the "canvas" button). This maps to 1536x864 (16:9). Wait 500ms. Fallback: iterate `.c-aspect-ratio .item` elements and match text "canvas".
7. **Click Generate** -- find a button containing "Generate" text with `x` in range 60-350 (left panel). Verify `!btn.disabled`. Click it. If blocked by dialog, close dialogs, wait 1000ms, retry once.
8. **Poll for result** -- snapshot result image count before generation (images matching `static.dzine.ai/stylar_product/p/` in src). Poll every 3 seconds. Detection: count images with src containing `gemini2text2image` or `faltxt2img`. If count increases OR total image count increases (fallback), generation is complete. Timeout: 120 seconds.
9. **Download result** -- extract `src` URL from the newest result image (lowest y-position = top of results panel). URL format: `https://static.dzine.ai/stylar_product/p/...`. Download via `urllib.request` with `User-Agent: Mozilla/5.0`. Timeout: 30 seconds.
10. **Save to disk** -- write to `{video_dir}/assets/dzine/thumbnail.png`. Create parent directories.
11. **Save prompt** -- write prompt text to `{video_dir}/assets/dzine/prompts/thumbnail.txt`.

### Prompt Template Reference

Use `PROMPT_TEMPLATES["thumbnail"]` from `tools/lib/dzine_schema.py`:
```
High-contrast YouTube thumbnail, 2048x1152 resolution.
Product: {product_name} prominently positioned, occupying ~70% of the frame...
```

### Validation

- [ ] File size > 50 KB (reject < 1024 bytes as download failure)
- [ ] Format: PNG or WebP
- [ ] Compute SHA-256 checksum via `_file_sha256()`
- [ ] Log generation time (expect 15-40s for Normal mode)

### Retry Logic

- On generation timeout or download failure: retry once from step 7 (Generate).
- If retry fails: call `close_all_dialogs(page)`, `_exit_tool_mode(page)`, refresh page via `page.goto(CANVAS_URL)`, wait 3000ms, restart from step 3.
- If second attempt fails: skip with warning, log error to `failed` list.

---

## SOP 2: PRODUCT IMAGE

Mode: Txt2Img | Ratio: 16:9 (hero/usage1/usage2/mood) or 1:1 (detail) | Model: per-variant routing
Variant system: hero, usage1, usage2, detail, mood per product.
Model selection: use `recommended_model("product", variant=variant)` from `dzine_schema.py`.
Default: Seedream 5.0 for hero/usage/mood, Nano Banana Pro for detail.

### Variant Allocation

| Rank | Variants | Count |
|------|----------|-------|
| 3-5 | hero, usage1, detail | 3 |
| 2 | hero, usage1, detail, mood | 4 |
| 1 | hero, usage1, detail, usage2, mood | 5 |

Use `variants_for_rank(rank)` from `dzine_schema.py` to determine which variants to generate.

### Preconditions

- [ ] Brave browser running with CDP on port 18800
- [ ] Logged in as Ramon Reis (Master plan)
- [ ] Canvas page loaded and viewport 1440x900
- [ ] `products.json` loaded with product name, rank, and optional `image_url`/`reference_image`

### Steps

1. **Close dialogs** -- `close_all_dialogs(page)`.
2. **Exit tool mode** -- `_exit_tool_mode(page)`.
3. **Activate Txt2Img panel** -- click Img2Img `(40, 252)` then Txt2Img `(40, 197)`. Verify `.gen-config-header` contains "Text to Image". Double-click fallback if needed.
4. **Select model** -- open style picker via `button.style`. Select the model from `recommended_model("product", variant=variant)` — default is "Seedream 4.5" for hero/usage/mood, "Nano Banana Pro" for detail. Escape to close.
5. **Build variant prompt** -- create a `DzineRequest`:
   ```python
   req = DzineRequest(
       asset_type="product",
       product_name=name,
       image_variant=variant,        # "hero", "usage1", "usage2", "detail", "mood"
       niche_category=category,      # from detect_category(niche)
       reference_image=ref_path,     # optional local path
   )
   req = build_prompts(req)
   ```
   This selects from `VARIANT_TEMPLATES[variant][category]` with fallback to `"default"`. Prompt includes product integrity prefix, scene, lighting, camera, mood, and restriction suffix. If `reference_image` is set, appends `_REF_PRESERVATION_SUFFIX`.
6. **Fill prompt** -- click `(101, 175)`, Cmd+A, type `req.prompt`. Max 1800 chars, 3ms delay.
7. **Set aspect ratio**:
   - hero, usage1, usage2, mood: click `.c-aspect-ratio .item.canvas` (16:9, 1536x864)
   - detail: click `.c-aspect-ratio button:has-text("1:1")` (square, 2048x2048)
8. **Click Generate** -- button "Generate" with x in 60-350, not disabled. Retry once after closing dialogs if blocked.
9. **Poll for result** -- same as Thumbnail SOP step 8. Poll every 3s, timeout 120s.
10. **Download result** -- fetch from `static.dzine.ai` URL. Save to `{video_dir}/assets/dzine/products/{rank:02d}_{variant}.png`.
11. **Save prompt** -- write to `{video_dir}/assets/dzine/prompts/{rank:02d}_{variant}.txt`.
12. **Pause** -- wait 2 seconds between product generations to avoid rate limiting.
13. **Repeat** -- loop for each variant of each product, sorted by rank ascending.

### Prompt Template Reference

Variant templates are in `VARIANT_TEMPLATES` dict in `tools/lib/dzine_schema.py`:
- **hero**: cinematic dark desk, 85mm shallow DOF, dramatic key light (category-independent)
- **usage1**: category-specific scene from `_USAGE1_SCENES` (e.g., "audio" = desk with neon glow)
- **usage2**: category-specific alternate scene from `_USAGE2_SCENES` (e.g., "audio" = airport/gym)
- **detail**: extreme macro close-up, side light, 1:1 square (category-independent)
- **mood**: atmospheric volumetric light, cinematic color grading (category-independent)

All prompts share prefix `_VARIANT_PREFIX` (product integrity) and suffix `_VARIANT_SUFFIX` (restrictions).

### Reference Image Upload (if available)

When `reference_image` path exists on disk:
- The prompt is automatically augmented with `_REF_PRESERVATION_SUFFIX` by `build_prompts()`.
- Reference image file should be pre-downloaded from Amazon to `assets/amazon/{rank:02d}_ref.jpg`.
- Dzine Txt2Img does NOT use a separate reference upload slot -- the reference instruction is embedded in the prompt text. The Img2Img mode would use a canvas layer, but product images use Txt2Img.
- If reference download failed: generate without reference (prompt still works, just less accurate).

> **WARNING:** Txt2Img generates *fictional* product images, not faithful recreations of the actual product. The AI invents a plausible-looking product based on the prompt, but it will NOT match the real Amazon product photo. This is acceptable for stylized/artistic product shots where exact fidelity is not required. For product-faithful visuals (preserving the real product appearance), use **SOP 5: PRODUCT_FAITHFUL** instead.

### Validation

- [ ] File size > 50 KB
- [ ] Format: PNG or WebP
- [ ] SHA-256 checksum logged
- [ ] Generation time logged (expect 15-40s Normal)

### Retry Logic

- On failure: retry once from step 8.
- On second failure: log to `failed` list, continue to next variant.
- After every 5 successful images: send Telegram progress via `notify_progress()`.

---

## SOP 3: BACKGROUND

Mode: Txt2Img | Ratio: 16:9 (canvas) | Model: Nano Banana Pro or Dzine General
Subtle gradient/atmosphere, no product, no reference image.

### Preconditions

- [ ] Brave browser running with CDP on port 18800
- [ ] Logged in as Ramon Reis (Master plan)
- [ ] Canvas page loaded and viewport 1440x900

### Steps

1. **Close dialogs** -- `close_all_dialogs(page)`.
2. **Exit tool mode** -- `_exit_tool_mode(page)`.
3. **Activate Txt2Img panel** -- toggle via Img2Img `(40, 252)` then Txt2Img `(40, 197)`. Verify header.
4. **Select model** -- open style picker, select "Nano Banana Pro" or "Dzine General". Escape to close.
5. **Fill prompt** -- click `(101, 175)`, Cmd+A, type `PROMPT_TEMPLATES["background"]`:
   ```
   Minimal cinematic background for a tech product ranking video, 2048x1152.
   Soft gradient lighting, subtle abstract shapes, smooth depth of field.
   Modern, clean, professional YouTube aesthetic.
   No text, no logos, no objects.
   High resolution, no artifacts.
   ```
6. **Set aspect ratio** -- click `.c-aspect-ratio .item.canvas` (16:9).
7. **Click Generate** -- button "Generate" x:60-350, not disabled. Retry once if blocked.
8. **Poll for result** -- poll every 3s, timeout 120s. Detect by image count increase.
9. **Download result** -- fetch from `static.dzine.ai` URL. Save to `{video_dir}/assets/dzine/background.png`.

### Prompt Template Reference

Use `PROMPT_TEMPLATES["background"]` from `tools/lib/dzine_schema.py`. No `{product_name}` substitution needed.

### Generation Settings

- Model: Nano Banana Pro (default) or Dzine General
- Quality: Normal (4 credits)
- Ratio: canvas (1536x864 = 16:9)
- No reference image
- No Face Match

### Validation

- [ ] File size > 50 KB
- [ ] Format: PNG or WebP
- [ ] No product or text visible (manual spot-check if needed)

### Retry Logic

- On failure: retry once from step 7.
- If retry fails: refresh page, restart from step 3.
- If second attempt fails: skip with warning.

---

## SOP 4: AVATAR_FRAME (Consistent Character -- Ray)

Mode: Consistent Character | Ratio: canvas (1536x864 = 16:9) | Produces 2 images per generation
Ray is the channel host. His identity is pre-saved in Dzine Character slot.

**CRITICAL: Canonical Face Reference**
Ray's definitive face is stored at `assets/ray_avatar/ray_reference_face.png`.
This face MUST be used as the CC Reference image in EVERY generation.
Code constant: `RAY_REFERENCE_FACE` in `tools/lib/dzine_browser.py`.
`generate_ray_scene()` auto-sets this as reference_image.
This face must remain identical across ALL creations — no exceptions.

### Preconditions

- [ ] Brave browser running with CDP on port 18800
- [ ] Logged in as Ramon Reis (Master plan)
- [ ] Canvas page loaded and viewport 1440x900
- [ ] "Ray" character previously saved in Dzine (Slot 1 of 60)
- [ ] `assets/ray_avatar/ray_reference_face.png` exists (canonical face)

### Steps

1. **Close dialogs** -- `close_all_dialogs(page)`.
2. **Exit tool mode** -- `_exit_tool_mode(page)`.
3. **Activate CC panel** -- double-click Character sidebar icon at `(40, 306)`. Wait 2000ms. Close any dialogs.
4. **Click "Generate Images" card** -- find element with text "Generate Images" where `x > 60`, `y` in 80-300, `height < 50`, `width > 50`. Click it. Wait 2000ms. Fallback: broader search for text containing both "Generate Images" and "With your".
5. **Select Ray character** -- use the hidden-list JS-click pattern:
   ```javascript
   // Primary: click button with exact text "Ray"
   for (const el of document.querySelectorAll('*')) {
       const t = (el.innerText || '').trim();
       if (t === 'Ray' && el.tagName === 'BUTTON') {
           el.click(); break;
       }
   }
   ```
   Wait 2000ms. Close dialogs.

   If the character list is a hidden/scrollable panel (`c-character-list`), use:
   ```javascript
   const items = document.querySelector('.c-character-list')
       .querySelectorAll('.item');
   // Find and click the item containing "Ray" text
   for (const item of items) {
       if ((item.innerText || '').trim().includes('Ray')) {
           item.click(); break;
       }
   }
   ```
6. **Verify CC panel active** -- check `.gen-config-header` contains "Consistent Character". If not found, retry: click Txt2Img `(40, 197)` wait 500ms, click Character `(40, 306)` wait 1500ms, then re-attempt "Generate Images" card click.
7. **Fill scene prompt** -- click at `(101, 200)` to focus the CC textarea. Cmd+A, then type the scene description. IMPORTANT: describe the SCENE, not the character. Ray's appearance is maintained automatically by the CC system.

   Example scene prompt: "Young adult male confidently presenting in a modern studio with soft cinematic lighting, subtle rim light, dark neutral background, professional tech reviewer setting."
8. **Set reference image (MANDATORY)** -- ALWAYS use `RAY_REFERENCE_FACE` (`assets/ray_avatar/ray_reference_face.png`) as reference. Call `_set_cc_reference(page, str(RAY_REFERENCE_FACE))`:
   - Click "Reference" button (y > 400, x: 60-350)
   - Click `button.pick-image` to open Pick Image dialog
   - Verify `.pick-panel` dialog opened
   - Click `button.upload` inside panel, intercept file chooser, set file
   - Verify reference set (`.image` div loses `empty` class)
   - To clear: click `.pick-image .ico-trash`
9. **Set aspect ratio** -- click the "canvas" button in the CC aspect ratio area:
   ```javascript
   for (const el of document.querySelectorAll('*')) {
       if ((el.innerText || '').trim() === 'canvas' &&
           el.getBoundingClientRect().x > 60 &&
           el.getBoundingClientRect().y > 400) {
           el.click(); break;
       }
   }
   ```
   This sets 1536x864 (16:9). Wait 500ms.
10. **Click Generate** -- find button containing "Generate", not disabled, with `x` in 60-350 and `y > 700`. Click it.
11. **Poll for result** -- CC generates 2 images per run. Snapshot total result image count before generation. Poll every 3s. When total count increases, generation is complete. Timeout: 120s. CC results may use `characterchatfal` or `faltxt2img` URL patterns -- detect by total count, not pattern.
12. **Download the better image** -- CC produces 2 results. The newest appears at the top of the results panel (lowest y). Download the first new result image from its `static.dzine.ai` URL. Save to `{video_dir}/assets/dzine/avatar_frame.png`.

### Prompt Template Reference

Use `PROMPT_TEMPLATES["avatar_base"]` from `dzine_schema.py` as a starting point, but adapt for scene context:
```
High-quality portrait of a confident modern host, 2048x2048.
Centered framing, clean studio lighting, neutral background.
Realistic skin texture, natural proportions, cinematic sharpness.
Friendly but subtle expression.
No watermark, no exaggerated facial features, no AI artifacts.
Tech reviewer aesthetic, subtle rim light, modern dark or neutral background.
```

For CC mode, simplify to scene-only (Ray's identity is automatic):
"Modern studio with soft cinematic key light, subtle rim light on edges, dark neutral blurred background. Tech reviewer standing pose, confident and approachable. Professional YouTube aesthetic."

### Generation Settings

- Mode: Consistent Character (4 credits per generation)
- Quality: Normal (default)
- Ratio: canvas (1536x864 = 16:9)
- Output: 2 images per generation (pick the best)
- Ray profile: young adult male, light skin, short dark hair, light stubble, charcoal gray t-shirt
- Canonical face: `assets/ray_avatar/ray_reference_face.png` (ALWAYS used as CC Reference)
- Face Swap fallback: `face_swap_ray()` in `dzine_browser.py` (4 credits, for post-hoc correction)
- Retrain character: `retrain_ray_character()` in `dzine_browser.py` (updates Dzine character slot)

### Export Steps

- Result images are available via their `static.dzine.ai` URLs in the Results panel.
- Download via `urllib.request` with User-Agent header.
- Alternatively, if download via URL fails: click the result image thumbnail, then click the download icon (4th button in the result preview actions row, selector `#result-preview button:nth-child(4)`).
- If Export button is disabled: click result image, click "Image Editor", activate first layer, then Export becomes enabled. Last resort: use the `static.dzine.ai` URL directly.

### Validation

- [ ] File size > 50 KB
- [ ] Format: PNG or WebP
- [ ] SHA-256 checksum computed and logged
- [ ] Generation time logged (expect 30-60s)

### Retry Logic

- On generation timeout: close dialogs, `_exit_tool_mode(page)`, retry from step 3.
- On download failure: try the second CC result image (there are always 2).
- If both fail: refresh page via `page.goto(CANVAS_URL)`, wait 3000ms, restart from step 1.
- Max 1 full retry. If second attempt fails: skip with warning, log error.

---

## SOP 5: PRODUCT_FAITHFUL

Mode: BG Remove + Generative Expand (NOT Img2Img) | Ratio: 16:9 | Credits: 8 per expand + 4 per enhance
Preserves the real product appearance from Amazon photos. Img2Img does NOT work for this -- even at 98% Structure Match it generates completely different objects.

**End-to-end timing (P137 confirmed):** BG Remove (~11s) + Generative Expand (~75s for 4 results) + Download = **~82-138s total** depending on expand timing. Each "Start from an image" creates a NEW project with URL `dzine.ai/canvas?id={project_id}`.

### Preconditions

- [ ] Brave browser running with CDP on port 18800
- [ ] Logged in as Ramon Reis (Master plan)
- [ ] Amazon product photo downloaded to local disk (e.g., `assets/amazon/{rank:02d}_ref.jpg`)

### Steps

1. **Navigate to Dzine home** -- `page.goto("https://www.dzine.ai/home")`. Wait for page load.
2. **Close dialogs** -- `close_all_dialogs(page)`.
3. **Create project from image** -- click the "Start from an image" button (`.project-item` containing text "start from an image", at approximately (435, 469) on home page). This triggers a native file chooser. NOTE: each click creates a NEW project with a unique ID.
   ```python
   start_btn = page.locator('.project-item:has-text("start from an image")').first
   with page.expect_file_chooser(timeout=5000) as fc_info:
       start_btn.click()
   fc = fc_info.value
   fc.set_files(str(product_image_path))
   ```
4. **Wait for canvas** -- Dzine redirects to `/canvas?id={new_id}` (each project gets a unique ID). Wait for at least 5 `.tool-group` elements: `page.wait_for_selector('.tool-group:nth-child(5)', timeout=15000)`. Set viewport to 1440x900.
5. **Close dialogs** -- `close_all_dialogs(page)`. May include project setup dialog (aspect ratio selection).
6. **BG Remove** -- click "BG Remove" in the action bar at the top of the canvas (y~95, after "AI Eraser", "Hand Repair", "Expression"). Takes ~11 seconds. 0 credits (free feature).
   ```python
   bg_btn = page.locator('button:has-text("BG Remove"), [class*="bg-remove"]').first
   bg_btn.click()
   ```
   Wait for "Removing background..." overlay to disappear (~11 seconds). Result: product isolated with transparent checkerboard background.
7. **Handle "Image Not Filling the Canvas" dialog** -- CRITICAL: after BG Remove, a modal dialog may appear saying "Image Not Filling the Canvas". This blocks ALL subsequent generation if not dismissed. Click the yellow "Fit to Content and Continue" button:
   ```python
   fit_btn = page.locator('button:has-text("Fit to Content and Continue")')
   if fit_btn.count() > 0 and fit_btn.first.is_visible(timeout=2000):
       fit_btn.first.click()
       page.wait_for_timeout(1000)
   ```
8. **Open Image Editor** -- click Image Editor in the left sidebar at `(40, 698)`. Wait 1500ms. Verify panel opens.
9. **Select Expand sub-tool** -- inside the Image Editor panel, click the "Expand" option (Generative Expand). Wait 1000ms.
10. **Set aspect ratio to 16:9** -- in the Expand panel, click the 16:9 aspect ratio button.
11. **Fill backdrop prompt** -- type the studio backdrop prompt:
    ```
    Clean white studio backdrop with soft professional lighting, subtle shadow underneath product
    ```
12. **Click Generate 8** -- the Generate 8 button is at approximately (212, 397) in the Expand panel. This costs 8 credits and produces 4 variants. IMPORTANT: distinguish this from other hidden Generate buttons elsewhere on the page -- target the one inside the Expand panel specifically.
    ```python
    # Target the Generate button inside the Image Editor / Expand panel
    gen_btn = page.locator('.collapse-panel button:has-text("Generate")')
    if gen_btn.count() > 0:
        gen_btn.first.click()
    ```
13. **Handle "Image Not Filling the Canvas" dialog again** -- this dialog may reappear after clicking Generate. Check and dismiss immediately:
    ```python
    fit_btn = page.locator('button:has-text("Fit to Content and Continue")')
    if fit_btn.count() > 0 and fit_btn.first.is_visible(timeout=2000):
        fit_btn.first.click()
    ```
14. **Poll for result** -- poll every 3 seconds. Generative Expand takes ~75 seconds and produces 4 variants. Timeout: 120 seconds. Detect completion by image count increase in the Results panel.
15. **Select best variant** -- review the 4 generated variants in the Results panel. Pick the one with the cleanest backdrop and best product visibility. Click it to place on canvas.
16. **Download result directly** -- extract `src` URL from the result image in the Results panel. URL follows standard `static.dzine.ai/stylar_product/p/{project_id}/...` pattern. Download via `urllib.request` with User-Agent header. Result is WebP format (~226KB typical).
    ```python
    # Get newest result image URL
    url = page.evaluate("""() => {
        var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
        if (imgs.length === 0) return null;
        return imgs[imgs.length - 1].src;
    }""")
    # Download via urllib
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    with open(output_path, "wb") as f:
        f.write(data)
    ```
17. **Save to disk** -- save to `{video_dir}/assets/dzine/products/{rank:02d}_faithful.webp` (or `.png` if using Export).

### Optional: Enhance & Upscale (via Results Panel -- CONFIRMED P138b/P139)

After expand completes, use the Results panel action buttons (NOT the sidebar) to upscale. This bypasses the locked-layer issue entirely.

1. **Click a numbered button next to "Enhance & Upscale"** in the Results panel. MUST use JavaScript click -- coordinates shift depending on sidebar state:
   ```python
   # Click Enhance & Upscale button [1] (first result) via JS
   page.evaluate("""() => {
       var btns = document.querySelectorAll('.btn-container .btn');
       // Find the Enhance & Upscale row's buttons
       for (var btn of btns) {
           var row = btn.closest('[class*="action"]') || btn.parentElement;
           if (row && (row.innerText || '').includes('Enhance')) {
               btn.click(); return true;
           }
       }
       return false;
   }""")
   ```
   **Button positions (approximate, shift by ~28px depending on sidebar state):**
   - Labels start at x=1120, width=146px, height=16px
   - Enhance & Upscale row: y=865-873 (sidebar panels open) or y=837-843 (sidebar panels closed)
   - [1] at x~1291, [2] at x~1328, [3] at x~1366, [4] at x~1403
   - Button class: `"btn"` (numbered) -- DO NOT click `"selected-btn"` (icon/label button opens sidebar, not popup)
   - Icon button at (1246, ~888) opens sidebar panel, NOT the popup -- avoid this

2. **Popup dialog opens** at center screen (~576-628, 236-292). Contains:
   - **Enhance Mode:** Precision (default) / Creative radio buttons
   - **Scale Factor:** 1.5x (default) / 2x / 3x / 4x buttons
   - **Format:** PNG (default) / JPG
   - **Upscale button** at approximately (600, 600) with text "Upscale\n4" (4 credits)
   ```python
   # Wait for popup to appear
   page.wait_for_timeout(2000)
   # Select 2x scale (optional -- default is 1.5x)
   page.evaluate("""() => {
       for (var el of document.querySelectorAll('button, [role="button"]')) {
           if ((el.innerText || '').trim() === '2x') { el.click(); return true; }
       }
       return false;
   }""")
   # Click Upscale button
   page.evaluate("""() => {
       for (var btn of document.querySelectorAll('button')) {
           if ((btn.innerText || '').includes('Upscale')) { btn.click(); return true; }
       }
       return false;
   }""")
   ```

3. **Poll for completion** -- enhance starts at 43% immediately, completes in ~25 seconds. Result count in the Results panel increments by 1.
   ```python
   before_count = page.locator('img[src*="static.dzine.ai/stylar_product/p/"]').count()
   # ... click Upscale ...
   import time
   start = time.time()
   while time.time() - start < 60:
       current = page.locator('img[src*="static.dzine.ai/stylar_product/p/"]').count()
       if current > before_count:
           break
       page.wait_for_timeout(3000)
   ```

4. **Download enhanced image** -- new image appears in Results panel. URL follows same `static.dzine.ai` pattern. At 1.5x scale, expect ~107KB; at 2x+, larger.

5. **Post-enhance note:** after completion, a "Chat Editor" input may appear at the bottom of the canvas. This is cosmetic and does not affect the workflow.

### Validation

- [ ] Exported file size > 50 KB (WebP direct download) or > 600 KB (PNG 2x export)
- [ ] Format: WebP (direct download) or PNG (export)
- [ ] Product in exported image visually matches the original Amazon photo
- [ ] Background is clean studio backdrop, not transparent checkerboard
- [ ] If enhanced: file size larger than pre-enhance version

### Credit Cost Summary

| Step | Credits |
|------|---------|
| BG Remove | 0 (free) |
| Generative Expand (4 results) | 8 |
| Enhance & Upscale (per image) | 4 |
| **Total (expand only)** | **8** |
| **Total (expand + enhance)** | **12** |

### Timing Reference (P137/P139 confirmed)

| Step | Duration |
|------|----------|
| BG Remove | ~11s |
| Generative Expand (4 results) | ~75s |
| Enhance & Upscale | ~25s |
| Direct download | ~2s |
| **Total (expand only)** | **~82-90s** |
| **Total (expand + enhance)** | **~107-138s** |

### Retry Logic

- If BG Remove fails: refresh page, re-upload image, retry.
- If Generative Expand stalls: check for "Image Not Filling the Canvas" dialog, dismiss it, retry Generate.
- If direct download produces a small file (<1 KB): wait 5s, re-download from URL. If still small, use Export dialog as fallback.
- If Enhance popup does not open: retry JS click on a different numbered button [2], [3], [4].
- If 2x scale button does not register: use default 1.5x scale (still useful improvement).
- Max 1 full retry. If second attempt fails: skip with warning, fall back to SOP 2 (Txt2Img) for this product.

---

## SOP 6: CHARACTER SHEET PIPELINE (Consistent Scenes from Reference Photo)

Mode: Txt2Img (Create Image) | Model: Nano Banana Pro | Ratio: 16:9 | Credits: 20 per generation (2K)
Technique discovered from official Dzine video f4HcdR3cd4M ("Consistent Character Sheets in Nano Banana").

### Purpose

Generate a multi-pose character sheet from a reference photo, then use that sheet as an "ingredient" for all subsequent scene generations. This ensures character consistency across every frame of a video without relying on the CC (Consistent Character) system.

### Preconditions

- [ ] Brave browser running with CDP on port 18800
- [ ] Logged in as Ramon Reis (Master plan)
- [ ] Canvas page loaded and viewport 1440x900
- [ ] Reference photo of character available on disk (e.g., `assets/ray_avatar/ray_reference_face.png`)

### Steps

1. **Close dialogs** -- `close_all_dialogs(page)`.
2. **Exit tool mode** -- `_exit_tool_mode(page)`.
3. **Activate Txt2Img panel** -- click Img2Img `(40, 252)` then Txt2Img `(40, 197)`. Verify `.gen-config-header` contains "Text to Image". This is the "Create Image" mode.
4. **Select Nano Banana Pro** -- open style picker via `button.style`. Find and click "Nano Banana Pro". Press Escape to close picker. Wait 1000ms.
5. **Set aspect ratio to 16:9** -- click the 16:9 option in `.c-aspect-ratio`. This produces 2720x1530 at 2K quality. Wait 500ms.
6. **Set output to x2** -- ensure "2 outputs" is selected so two character sheet variants are generated per run.
7. **Upload reference photo** -- use the reference image upload slot (if available in Txt2Img mode) or include the reference description in the prompt. For Nano Banana Pro Txt2Img, reference is embedded in prompt text.
8. **Fill character sheet prompt** -- click `(101, 175)`, Cmd+A, type the character sheet prompt:
   ```
   Character reference sheet of [character description], showing front view, left side view, right side view, and back view in the top row. Bottom row shows face close-ups with different expressions: neutral, smiling, serious, surprised. White background, clean illustration style, consistent proportions and features across all views. Full body poses in top row, head-and-shoulders in bottom row. Professional character design reference.
   ```
   Replace `[character description]` with the specific character details (age, build, hair, clothing, etc.).
9. **Click Generate** -- button "Generate" with x in 60-350, not disabled. Cost: 20 credits at 2K. Wait for generation.
10. **Poll for result** -- poll every 3s, timeout 120s. Detect by image count increase.
11. **Select best sheet** -- review the 2 generated character sheets. Pick the one with the most consistent proportions and clearest views across all poses.
12. **Click "Add To Prompt"** -- CRITICAL STEP. Click the "Add To Prompt" action on the selected character sheet result. This adds the sheet as an "ingredient" for all subsequent generations. The sheet image will appear as a reference thumbnail in the prompt area.
13. **Generate scene** -- now write a SCENE prompt (not a character prompt). The character's identity is maintained by the ingredient sheet. Example:
    ```
    [Character name] walking through a modern kitchen, morning light streaming through windows, casual pose, photorealistic, 8K detail
    ```
14. **Click Generate** -- the scene will feature the character with consistent appearance from the sheet.
15. **Download result** -- fetch from `static.dzine.ai` URL. Save to desired output path.

### CRITICAL RULES

1. **ALWAYS include the character sheet as ingredient** -- even when a start frame or other reference already exists. Without the sheet as ingredient, character consistency degrades significantly across generations.
2. **Scene prompts only** -- when the sheet is loaded as ingredient, describe only the SCENE and ACTION, not the character's physical features. The sheet handles identity.
3. **Two-character scenes** -- for scenes with two characters, upload BOTH character reference sheets as ingredients. Both characters will appear with consistent identities.
4. **Wardrobe changes** -- to change outfits while keeping the same character, generate a NEW character sheet with the different outfit in the prompt. The face/body stay consistent; only clothing changes. Then use the new sheet as ingredient.

### Validation

- [ ] Character sheet shows at least 4 distinct poses (front/left/right/back)
- [ ] Face close-ups show consistent facial features
- [ ] Scene generations match the character sheet identity
- [ ] File size > 50 KB per output

### Retry Logic

- If character sheet has inconsistent faces across views: regenerate with more specific facial feature description in prompt.
- If "Add To Prompt" button not found: try clicking the result image first to select it, then look for the action button.
- Max 2 attempts per character sheet. If both fail: fall back to SOP 4 (CC mode with Ray character).

---

## Common Notes

### AI Video Credit Costs (model-dependent)

| Model | Credits | Duration |
|-------|---------|----------|
| Wan 2.1 | 6 | 5s |
| Seedance Pro Fast | 7-35 | 5s |
| Wan 2.5 | 7-21 | /s |
| Dzine Video V1 | 10 | 5s |
| Seedance 1.5 Pro | 12-56 | 5s |
| Dzine Video V2 | 20 | 5s |
| Kling 2.5 Turbo STD | 30 | 5s |
| Runway Gen4 turbo | 46 | 5s |
| Minimax Hailuo 2.3 | 56-98 | 6s |
| Sora 2 | 100 | 4s |
| Google Veo 3.1 Fast | 200-304 | 8s |

Video credits are separate from image credits. Master plan includes 8.850 video credits.

### Session Management

- Use `_get_or_create_page()` to get a reusable Playwright page. Reconnects automatically on stale connections.
- Call `close_session()` after a batch of operations to clean up.
- Between batch images, pause 2 seconds to avoid rate limiting.

### Progress Notifications

- Send Telegram notification via `notify_progress(video_id, "assets", message)` every 5 images.
- Include count of generated and failed images in the message.

### File Naming Convention

```
assets/dzine/thumbnail.png
assets/dzine/background.png
assets/dzine/avatar_frame.png
assets/dzine/products/05_hero.png
assets/dzine/products/05_usage1.png
assets/dzine/products/05_detail.png
assets/dzine/products/02_mood.png
assets/dzine/products/01_usage2.png
assets/dzine/products/01_mood.png
assets/dzine/prompts/thumbnail.txt
assets/dzine/prompts/05_hero.txt
```

Rank is zero-padded to 2 digits. Variants are lowercase.

### Generation Timing Reference

| Mode | Expected Time |
|------|--------------|
| Txt2Img Fast | 15-20s |
| Txt2Img Normal | 30-40s |
| Txt2Img HQ | 50-120s |
| CC Normal | 30-60s |
| BG Remove | ~11s |
| Generative Expand (4 results) | ~75s |
| Enhance & Upscale | ~25s |
| Product Faithful end-to-end | ~82-138s |

### Error Escalation

1. Close dialogs and retry the Generate click.
2. Exit tool mode, re-activate the correct panel, retry.
3. Refresh the full canvas page, retry from panel activation.
4. Skip the image, log to `failed` list, continue to next.

Never attempt more than 1 full retry per image. Total pipeline must not stall on a single asset.
