---
description: Auto-recorded lessons from pipeline runs. Newest first. Check this BEFORE every pipeline run to avoid repeating mistakes.
tags: [moc, learnings, auto-improvement, memory]
created: 2026-02-19
updated: 2026-02-19
---

# Learnings (Auto-Improvement Log)

Every pipeline run records its outcome here. Before starting any generation, the agent MUST scan this index to avoid repeating documented failures.

## Protocol

1. **Before run**: Read this index. Check for relevant failures.
2. **After run**: Create new learning node with date prefix.
3. **If prompt failed**: Mark old prompt as `status: deprecated`, create improved version.
4. **If tool was wrong**: Update tool node with failure context.
5. **Format**: `YYYY-MM-DD-short-description.md`

## Recent Learnings (newest first)

- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-fail-research-test-77]] — cause → fix
- [[2026-02-19-fail-research-test-76]] — cause → fix
- [[2026-02-19-fail-research-test-75]] — cause → fix
- [[2026-02-19-fail-research-test-74]] — cause → fix
- [[2026-02-19-fail-research-test-73]] — cause → fix
- [[2026-02-19-fail-research-test-72]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-22]] — No price validation → Added price anomaly check
- [[2026-02-19-fail-assets-s3-77]] — c3 → f3
- [[2026-02-19-warn-assets-s2-77]] — c2 → f2
- [[2026-02-19-fail-research-s1-77]] — c1 → f1
- [[2026-02-19-fail-assets-s3-76]] — c3 → f3
- [[2026-02-19-warn-assets-s2-76]] — c2 → f2
- [[2026-02-19-fail-research-s1-76]] — c1 → f1
- [[2026-02-19-fail-assets-s3-75]] — c3 → f3
- [[2026-02-19-warn-assets-s2-75]] — c2 → f2
- [[2026-02-19-fail-research-s1-75]] — c1 → f1
- [[2026-02-19-fail-assets-s3-74]] — c3 → f3
- [[2026-02-19-warn-assets-s2-74]] — c2 → f2
- [[2026-02-19-fail-research-s1-74]] — c1 → f1
- [[2026-02-19-fail-assets-s3-73]] — c3 → f3
- [[2026-02-19-warn-assets-s2-73]] — c2 → f2
- [[2026-02-19-fail-research-s1-73]] — c1 → f1
- [[2026-02-19-fail-assets-s3-72]] — c3 → f3
- [[2026-02-19-warn-assets-s2-72]] — c2 → f2
- [[2026-02-19-fail-research-s1-72]] — c1 → f1
- [[2026-02-19-fail-assets-s3-71]] — c3 → f3
- [[2026-02-19-warn-assets-s2-71]] — c2 → f2
- [[2026-02-19-fail-research-s1-71]] — c1 → f1
- [[2026-02-19-warn-tts-audio-clipping-11]] — Volume too high → Reduced volume by 3dB
- [[2026-02-19-fail-assets-image-hallucination-11]] — Changed reference angle → Reverted to original angle
- [[2026-02-19-fail-research-test-71]] — cause → fix
- [[2026-02-19-warn-dzine-phone-ghost-in-bg-remove-11]] — Ref had phone → Used drawbox to blank phone area
- [[2026-02-19-info-research-symptom-2-11]] — cause → fix
- [[2026-02-19-info-research-symptom-1-11]] — cause → fix
- [[2026-02-19-info-research-symptom-0-11]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-21]] — No price validation → Added price anomaly check
- [[2026-02-19-fail-unknown-v038-asin-accessories-detected-by-price-anomaly]] — No price validation existed. The researcher accepted the ASIN without checking if the price was reasonable for the category. → - Added price anomaly detection: flag products with price <30% of category median
- Added accessory keyword filter: detect "replacement", "kit", "pack of", etc. in product names
- Added duplicate evid
- [[2026-02-19-blocker-unknown-playwright-asyncio-crash]] — Each `generate_product_faithful()` call was creating a new `sync_playwright().start()`. The second call detected an existing event loop from the first Playwright instance. → Module-level shared session globals. See [[../dzine/shared-session]] for full pattern.

After fix: all 18 images generated without crashes.

- [[2026-02-19-warn-unknown-phone-removal-from-reference-images]] — BG Remove classifies all foreground objects as "product" — it can't distinguish between the main product and accessories in the frame. → Two strategies, both successful:

### Strategy 1: Crop reference (products 01, 04, 05)

Used ffmpeg to crop the phone out before uploading:

```bash
/opt/homebrew/bin/ffmpeg -i original.jpg -vf "crop=
- [[2026-02-19-blocker-unknown-identical-images-from-generative-expand]] — Generative Expand is a **canvas extension tool**, NOT a scene generator. It fills the expanded area by continuing the edge pixels of the existing image. The prompt field exists but has minimal influen → Replace Generative Expand with **Product Background** tool in the pipeline:

1. Product Background is designed specifically for scene generation
2. It accepts and respects scene prompts
3. It handles
- [[2026-02-19-fail-unknown-generated-image-added-a-second-charging-dock-that-did-not-ex]] — Reference image had visual clutter and ambiguous shapes near the dock area. Generation model interpreted the pattern as an extra dock. → 1. Switched to a cleaner alternate Amazon reference.
2. Cropped reference tighter around product + real dock.
3. Re-generated with explicit prompt constraint: one dock only.
- [[2026-02-19-fail-unknown-product-background-generation-timed-out-at-43-progress-a-d]] — Product Background does NOT handle BG removal internally (contrary to initial assumption from Dzine marketing). It requires the image to already have a transparent/empty background before it will gene → 1. Updated `generate_product_faithful()` to run `_bg_remove()` before `_product_background()`
2. Added "Done" to `close_all_dialogs()` dismiss texts to handle the error dialog
3. After fix: 4 result i
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-fail-research-test-70]] — cause → fix
- [[2026-02-19-fail-research-test-69]] — cause → fix
- [[2026-02-19-fail-research-test-68]] — cause → fix
- [[2026-02-19-fail-research-test-67]] — cause → fix
- [[2026-02-19-fail-research-test-66]] — cause → fix
- [[2026-02-19-fail-research-test-65]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-20]] — No price validation → Added price anomaly check
- [[2026-02-19-fail-assets-s3-70]] — c3 → f3
- [[2026-02-19-warn-assets-s2-70]] — c2 → f2
- [[2026-02-19-fail-research-s1-70]] — c1 → f1
- [[2026-02-19-fail-assets-s3-69]] — c3 → f3
- [[2026-02-19-warn-assets-s2-69]] — c2 → f2
- [[2026-02-19-fail-research-s1-69]] — c1 → f1
- [[2026-02-19-fail-assets-s3-68]] — c3 → f3
- [[2026-02-19-warn-assets-s2-68]] — c2 → f2
- [[2026-02-19-fail-research-s1-68]] — c1 → f1
- [[2026-02-19-fail-assets-s3-67]] — c3 → f3
- [[2026-02-19-warn-assets-s2-67]] — c2 → f2
- [[2026-02-19-fail-research-s1-67]] — c1 → f1
- [[2026-02-19-fail-assets-s3-66]] — c3 → f3
- [[2026-02-19-warn-assets-s2-66]] — c2 → f2
- [[2026-02-19-fail-research-s1-66]] — c1 → f1
- [[2026-02-19-fail-assets-s3-65]] — c3 → f3
- [[2026-02-19-warn-assets-s2-65]] — c2 → f2
- [[2026-02-19-fail-research-s1-65]] — c1 → f1
- [[2026-02-19-fail-assets-s3-64]] — c3 → f3
- [[2026-02-19-warn-assets-s2-64]] — c2 → f2
- [[2026-02-19-fail-research-s1-64]] — c1 → f1
- [[2026-02-19-warn-tts-audio-clipping-10]] — Volume too high → Reduced volume by 3dB
- [[2026-02-19-fail-assets-image-hallucination-10]] — Changed reference angle → Reverted to original angle
- [[2026-02-19-fail-research-test-64]] — cause → fix
- [[2026-02-19-warn-dzine-phone-ghost-in-bg-remove-10]] — Ref had phone → Used drawbox to blank phone area
- [[2026-02-19-info-research-symptom-2-10]] — cause → fix
- [[2026-02-19-info-research-symptom-1-10]] — cause → fix
- [[2026-02-19-info-research-symptom-0-10]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-19]] — No price validation → Added price anomaly check
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-fail-research-test-63]] — cause → fix
- [[2026-02-19-fail-research-test-62]] — cause → fix
- [[2026-02-19-fail-research-test-61]] — cause → fix
- [[2026-02-19-fail-research-test-60]] — cause → fix
- [[2026-02-19-fail-research-test-59]] — cause → fix
- [[2026-02-19-fail-research-test-58]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-18]] — No price validation → Added price anomaly check
- [[2026-02-19-fail-assets-s3-63]] — c3 → f3
- [[2026-02-19-warn-assets-s2-63]] — c2 → f2
- [[2026-02-19-fail-research-s1-63]] — c1 → f1
- [[2026-02-19-fail-assets-s3-62]] — c3 → f3
- [[2026-02-19-warn-assets-s2-62]] — c2 → f2
- [[2026-02-19-fail-research-s1-62]] — c1 → f1
- [[2026-02-19-fail-assets-s3-61]] — c3 → f3
- [[2026-02-19-warn-assets-s2-61]] — c2 → f2
- [[2026-02-19-fail-research-s1-61]] — c1 → f1
- [[2026-02-19-fail-assets-s3-60]] — c3 → f3
- [[2026-02-19-warn-assets-s2-60]] — c2 → f2
- [[2026-02-19-fail-research-s1-60]] — c1 → f1
- [[2026-02-19-fail-assets-s3-59]] — c3 → f3
- [[2026-02-19-warn-assets-s2-59]] — c2 → f2
- [[2026-02-19-fail-research-s1-59]] — c1 → f1
- [[2026-02-19-fail-assets-s3-58]] — c3 → f3
- [[2026-02-19-warn-assets-s2-58]] — c2 → f2
- [[2026-02-19-fail-research-s1-58]] — c1 → f1
- [[2026-02-19-fail-assets-s3-57]] — c3 → f3
- [[2026-02-19-warn-assets-s2-57]] — c2 → f2
- [[2026-02-19-fail-research-s1-57]] — c1 → f1
- [[2026-02-19-warn-tts-audio-clipping-9]] — Volume too high → Reduced volume by 3dB
- [[2026-02-19-fail-assets-image-hallucination-9]] — Changed reference angle → Reverted to original angle
- [[2026-02-19-fail-research-test-57]] — cause → fix
- [[2026-02-19-warn-dzine-phone-ghost-in-bg-remove-9]] — Ref had phone → Used drawbox to blank phone area
- [[2026-02-19-info-research-symptom-2-9]] — cause → fix
- [[2026-02-19-info-research-symptom-1-9]] — cause → fix
- [[2026-02-19-info-research-symptom-0-9]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-17]] — No price validation → Added price anomaly check
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-fail-research-test-56]] — cause → fix
- [[2026-02-19-fail-research-test-55]] — cause → fix
- [[2026-02-19-fail-research-test-54]] — cause → fix
- [[2026-02-19-fail-research-test-53]] — cause → fix
- [[2026-02-19-fail-research-test-52]] — cause → fix
- [[2026-02-19-fail-research-test-51]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-16]] — No price validation → Added price anomaly check
- [[2026-02-19-fail-assets-s3-56]] — c3 → f3
- [[2026-02-19-warn-assets-s2-56]] — c2 → f2
- [[2026-02-19-fail-research-s1-56]] — c1 → f1
- [[2026-02-19-fail-assets-s3-55]] — c3 → f3
- [[2026-02-19-warn-assets-s2-55]] — c2 → f2
- [[2026-02-19-fail-research-s1-55]] — c1 → f1
- [[2026-02-19-fail-assets-s3-54]] — c3 → f3
- [[2026-02-19-warn-assets-s2-54]] — c2 → f2
- [[2026-02-19-fail-research-s1-54]] — c1 → f1
- [[2026-02-19-fail-assets-s3-53]] — c3 → f3
- [[2026-02-19-warn-assets-s2-53]] — c2 → f2
- [[2026-02-19-fail-research-s1-53]] — c1 → f1
- [[2026-02-19-fail-assets-s3-52]] — c3 → f3
- [[2026-02-19-warn-assets-s2-52]] — c2 → f2
- [[2026-02-19-fail-research-s1-52]] — c1 → f1
- [[2026-02-19-fail-assets-s3-51]] — c3 → f3
- [[2026-02-19-warn-assets-s2-51]] — c2 → f2
- [[2026-02-19-fail-research-s1-51]] — c1 → f1
- [[2026-02-19-fail-assets-s3-50]] — c3 → f3
- [[2026-02-19-warn-assets-s2-50]] — c2 → f2
- [[2026-02-19-fail-research-s1-50]] — c1 → f1
- [[2026-02-19-warn-tts-audio-clipping-8]] — Volume too high → Reduced volume by 3dB
- [[2026-02-19-fail-assets-image-hallucination-8]] — Changed reference angle → Reverted to original angle
- [[2026-02-19-fail-research-test-50]] — cause → fix
- [[2026-02-19-warn-dzine-phone-ghost-in-bg-remove-8]] — Ref had phone → Used drawbox to blank phone area
- [[2026-02-19-info-research-symptom-2-8]] — cause → fix
- [[2026-02-19-info-research-symptom-1-8]] — cause → fix
- [[2026-02-19-info-research-symptom-0-8]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-15]] — No price validation → Added price anomaly check
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-fail-research-test-49]] — cause → fix
- [[2026-02-19-fail-research-test-48]] — cause → fix
- [[2026-02-19-fail-research-test-47]] — cause → fix
- [[2026-02-19-fail-research-test-46]] — cause → fix
- [[2026-02-19-fail-research-test-45]] — cause → fix
- [[2026-02-19-fail-research-test-44]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-14]] — No price validation → Added price anomaly check
- [[2026-02-19-fail-assets-s3-49]] — c3 → f3
- [[2026-02-19-warn-assets-s2-49]] — c2 → f2
- [[2026-02-19-fail-research-s1-49]] — c1 → f1
- [[2026-02-19-fail-assets-s3-48]] — c3 → f3
- [[2026-02-19-warn-assets-s2-48]] — c2 → f2
- [[2026-02-19-fail-research-s1-48]] — c1 → f1
- [[2026-02-19-fail-assets-s3-47]] — c3 → f3
- [[2026-02-19-warn-assets-s2-47]] — c2 → f2
- [[2026-02-19-fail-research-s1-47]] — c1 → f1
- [[2026-02-19-fail-assets-s3-46]] — c3 → f3
- [[2026-02-19-warn-assets-s2-46]] — c2 → f2
- [[2026-02-19-fail-research-s1-46]] — c1 → f1
- [[2026-02-19-fail-assets-s3-45]] — c3 → f3
- [[2026-02-19-warn-assets-s2-45]] — c2 → f2
- [[2026-02-19-fail-research-s1-45]] — c1 → f1
- [[2026-02-19-fail-assets-s3-44]] — c3 → f3
- [[2026-02-19-warn-assets-s2-44]] — c2 → f2
- [[2026-02-19-fail-research-s1-44]] — c1 → f1
- [[2026-02-19-fail-assets-s3-43]] — c3 → f3
- [[2026-02-19-warn-assets-s2-43]] — c2 → f2
- [[2026-02-19-fail-research-s1-43]] — c1 → f1
- [[2026-02-19-warn-tts-audio-clipping-7]] — Volume too high → Reduced volume by 3dB
- [[2026-02-19-fail-assets-image-hallucination-7]] — Changed reference angle → Reverted to original angle
- [[2026-02-19-fail-research-test-43]] — cause → fix
- [[2026-02-19-warn-dzine-phone-ghost-in-bg-remove-7]] — Ref had phone → Used drawbox to blank phone area
- [[2026-02-19-info-research-symptom-2-7]] — cause → fix
- [[2026-02-19-info-research-symptom-1-7]] — cause → fix
- [[2026-02-19-info-research-symptom-0-7]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-13]] — No price validation → Added price anomaly check
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-fail-research-test-42]] — cause → fix
- [[2026-02-19-fail-research-test-41]] — cause → fix
- [[2026-02-19-fail-research-test-40]] — cause → fix
- [[2026-02-19-fail-research-test-39]] — cause → fix
- [[2026-02-19-fail-research-test-38]] — cause → fix
- [[2026-02-19-fail-research-test-37]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-12]] — No price validation → Added price anomaly check
- [[2026-02-19-fail-assets-s3-42]] — c3 → f3
- [[2026-02-19-warn-assets-s2-42]] — c2 → f2
- [[2026-02-19-fail-research-s1-42]] — c1 → f1
- [[2026-02-19-fail-assets-s3-41]] — c3 → f3
- [[2026-02-19-warn-assets-s2-41]] — c2 → f2
- [[2026-02-19-fail-research-s1-41]] — c1 → f1
- [[2026-02-19-fail-assets-s3-40]] — c3 → f3
- [[2026-02-19-warn-assets-s2-40]] — c2 → f2
- [[2026-02-19-fail-research-s1-40]] — c1 → f1
- [[2026-02-19-fail-assets-s3-39]] — c3 → f3
- [[2026-02-19-warn-assets-s2-39]] — c2 → f2
- [[2026-02-19-fail-research-s1-39]] — c1 → f1
- [[2026-02-19-fail-assets-s3-38]] — c3 → f3
- [[2026-02-19-warn-assets-s2-38]] — c2 → f2
- [[2026-02-19-fail-research-s1-38]] — c1 → f1
- [[2026-02-19-fail-assets-s3-37]] — c3 → f3
- [[2026-02-19-warn-assets-s2-37]] — c2 → f2
- [[2026-02-19-fail-research-s1-37]] — c1 → f1
- [[2026-02-19-fail-assets-s3-36]] — c3 → f3
- [[2026-02-19-warn-assets-s2-36]] — c2 → f2
- [[2026-02-19-fail-research-s1-36]] — c1 → f1
- [[2026-02-19-warn-tts-audio-clipping-6]] — Volume too high → Reduced volume by 3dB
- [[2026-02-19-fail-assets-image-hallucination-6]] — Changed reference angle → Reverted to original angle
- [[2026-02-19-fail-research-test-36]] — cause → fix
- [[2026-02-19-warn-dzine-phone-ghost-in-bg-remove-6]] — Ref had phone → Used drawbox to blank phone area
- [[2026-02-19-info-research-symptom-2-6]] — cause → fix
- [[2026-02-19-info-research-symptom-1-6]] — cause → fix
- [[2026-02-19-info-research-symptom-0-6]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-11]] — No price validation → Added price anomaly check
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-fail-research-test-35]] — cause → fix
- [[2026-02-19-fail-research-test-34]] — cause → fix
- [[2026-02-19-fail-research-test-33]] — cause → fix
- [[2026-02-19-fail-research-test-32]] — cause → fix
- [[2026-02-19-fail-research-test-31]] — cause → fix
- [[2026-02-19-fail-research-test-30]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-10]] — No price validation → Added price anomaly check
- [[2026-02-19-fail-assets-s3-35]] — c3 → f3
- [[2026-02-19-warn-assets-s2-35]] — c2 → f2
- [[2026-02-19-fail-research-s1-35]] — c1 → f1
- [[2026-02-19-fail-assets-s3-34]] — c3 → f3
- [[2026-02-19-warn-assets-s2-34]] — c2 → f2
- [[2026-02-19-fail-research-s1-34]] — c1 → f1
- [[2026-02-19-fail-assets-s3-33]] — c3 → f3
- [[2026-02-19-warn-assets-s2-33]] — c2 → f2
- [[2026-02-19-fail-research-s1-33]] — c1 → f1
- [[2026-02-19-fail-assets-s3-32]] — c3 → f3
- [[2026-02-19-warn-assets-s2-32]] — c2 → f2
- [[2026-02-19-fail-research-s1-32]] — c1 → f1
- [[2026-02-19-fail-assets-s3-31]] — c3 → f3
- [[2026-02-19-warn-assets-s2-31]] — c2 → f2
- [[2026-02-19-fail-research-s1-31]] — c1 → f1
- [[2026-02-19-fail-assets-s3-30]] — c3 → f3
- [[2026-02-19-warn-assets-s2-30]] — c2 → f2
- [[2026-02-19-fail-research-s1-30]] — c1 → f1
- [[2026-02-19-fail-assets-s3-29]] — c3 → f3
- [[2026-02-19-warn-assets-s2-29]] — c2 → f2
- [[2026-02-19-fail-research-s1-29]] — c1 → f1
- [[2026-02-19-warn-tts-audio-clipping-5]] — Volume too high → Reduced volume by 3dB
- [[2026-02-19-fail-assets-image-hallucination-5]] — Changed reference angle → Reverted to original angle
- [[2026-02-19-fail-research-test-29]] — cause → fix
- [[2026-02-19-warn-dzine-phone-ghost-in-bg-remove-5]] — Ref had phone → Used drawbox to blank phone area
- [[2026-02-19-info-research-symptom-2-5]] — cause → fix
- [[2026-02-19-info-research-symptom-1-5]] — cause → fix
- [[2026-02-19-info-research-symptom-0-5]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-9]] — No price validation → Added price anomaly check
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-fail-research-test-28]] — cause → fix
- [[2026-02-19-fail-research-test-27]] — cause → fix
- [[2026-02-19-fail-research-test-26]] — cause → fix
- [[2026-02-19-fail-research-test-25]] — cause → fix
- [[2026-02-19-fail-research-test-24]] — cause → fix
- [[2026-02-19-fail-research-test-23]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-8]] — No price validation → Added price anomaly check
- [[2026-02-19-fail-assets-s3-28]] — c3 → f3
- [[2026-02-19-warn-assets-s2-28]] — c2 → f2
- [[2026-02-19-fail-research-s1-28]] — c1 → f1
- [[2026-02-19-fail-assets-s3-27]] — c3 → f3
- [[2026-02-19-warn-assets-s2-27]] — c2 → f2
- [[2026-02-19-fail-research-s1-27]] — c1 → f1
- [[2026-02-19-fail-assets-s3-26]] — c3 → f3
- [[2026-02-19-warn-assets-s2-26]] — c2 → f2
- [[2026-02-19-fail-research-s1-26]] — c1 → f1
- [[2026-02-19-fail-assets-s3-25]] — c3 → f3
- [[2026-02-19-warn-assets-s2-25]] — c2 → f2
- [[2026-02-19-fail-research-s1-25]] — c1 → f1
- [[2026-02-19-fail-assets-s3-24]] — c3 → f3
- [[2026-02-19-warn-assets-s2-24]] — c2 → f2
- [[2026-02-19-fail-research-s1-24]] — c1 → f1
- [[2026-02-19-fail-assets-s3-23]] — c3 → f3
- [[2026-02-19-warn-assets-s2-23]] — c2 → f2
- [[2026-02-19-fail-research-s1-23]] — c1 → f1
- [[2026-02-19-fail-assets-s3-22]] — c3 → f3
- [[2026-02-19-warn-assets-s2-22]] — c2 → f2
- [[2026-02-19-fail-research-s1-22]] — c1 → f1
- [[2026-02-19-warn-tts-audio-clipping-4]] — Volume too high → Reduced volume by 3dB
- [[2026-02-19-fail-assets-image-hallucination-4]] — Changed reference angle → Reverted to original angle
- [[2026-02-19-fail-research-test-22]] — cause → fix
- [[2026-02-19-warn-dzine-phone-ghost-in-bg-remove-4]] — Ref had phone → Used drawbox to blank phone area
- [[2026-02-19-info-research-symptom-2-4]] — cause → fix
- [[2026-02-19-info-research-symptom-1-4]] — cause → fix
- [[2026-02-19-info-research-symptom-0-4]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-7]] — No price validation → Added price anomaly check
- [[2026-02-19-fail-research-test-21]] — cause → fix
- [[2026-02-19-fail-research-test-20]] — cause → fix
- [[2026-02-19-fail-research-test-19]] — cause → fix
- [[2026-02-19-fail-research-test-18]] — cause → fix
- [[2026-02-19-fail-research-test-17]] — cause → fix
- [[2026-02-19-fail-research-test-16]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-6]] — No price validation → Added price anomaly check
- [[2026-02-19-fail-assets-s3-21]] — c3 → f3
- [[2026-02-19-warn-assets-s2-21]] — c2 → f2
- [[2026-02-19-fail-research-s1-21]] — c1 → f1
- [[2026-02-19-fail-assets-s3-20]] — c3 → f3
- [[2026-02-19-warn-assets-s2-20]] — c2 → f2
- [[2026-02-19-fail-research-s1-20]] — c1 → f1
- [[2026-02-19-fail-assets-s3-19]] — c3 → f3
- [[2026-02-19-warn-assets-s2-19]] — c2 → f2
- [[2026-02-19-fail-research-s1-19]] — c1 → f1
- [[2026-02-19-fail-assets-s3-18]] — c3 → f3
- [[2026-02-19-warn-assets-s2-18]] — c2 → f2
- [[2026-02-19-fail-research-s1-18]] — c1 → f1
- [[2026-02-19-fail-assets-s3-17]] — c3 → f3
- [[2026-02-19-warn-assets-s2-17]] — c2 → f2
- [[2026-02-19-fail-research-s1-17]] — c1 → f1
- [[2026-02-19-fail-assets-s3-16]] — c3 → f3
- [[2026-02-19-warn-assets-s2-16]] — c2 → f2
- [[2026-02-19-fail-research-s1-16]] — c1 → f1
- [[2026-02-19-fail-assets-s3-15]] — c3 → f3
- [[2026-02-19-warn-assets-s2-15]] — c2 → f2
- [[2026-02-19-fail-research-s1-15]] — c1 → f1
- [[2026-02-19-warn-tts-audio-clipping-3]] — Volume too high → Reduced volume by 3dB
- [[2026-02-19-fail-assets-image-hallucination-3]] — Changed reference angle → Reverted to original angle
- [[2026-02-19-fail-research-test-15]] — cause → fix
- [[2026-02-19-warn-dzine-phone-ghost-in-bg-remove-3]] — Ref had phone → Used drawbox to blank phone area
- [[2026-02-19-info-research-symptom-2-3]] — cause → fix
- [[2026-02-19-info-research-symptom-1-3]] — cause → fix
- [[2026-02-19-info-research-symptom-0-3]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-5]] — No price validation → Added price anomaly check
- [[2026-02-19-fail-research-test-14]] — cause → fix
- [[2026-02-19-fail-research-test-13]] — cause → fix
- [[2026-02-19-fail-research-test-12]] — cause → fix
- [[2026-02-19-fail-research-test-11]] — cause → fix
- [[2026-02-19-fail-research-test-10]] — cause → fix
- [[2026-02-19-fail-research-test-9]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-4]] — No price validation → Added price anomaly check
- [[2026-02-19-fail-assets-s3-14]] — c3 → f3
- [[2026-02-19-warn-assets-s2-14]] — c2 → f2
- [[2026-02-19-fail-research-s1-14]] — c1 → f1
- [[2026-02-19-fail-assets-s3-13]] — c3 → f3
- [[2026-02-19-warn-assets-s2-13]] — c2 → f2
- [[2026-02-19-fail-research-s1-13]] — c1 → f1
- [[2026-02-19-fail-assets-s3-12]] — c3 → f3
- [[2026-02-19-warn-assets-s2-12]] — c2 → f2
- [[2026-02-19-fail-research-s1-12]] — c1 → f1
- [[2026-02-19-fail-assets-s3-11]] — c3 → f3
- [[2026-02-19-warn-assets-s2-11]] — c2 → f2
- [[2026-02-19-fail-research-s1-11]] — c1 → f1
- [[2026-02-19-fail-assets-s3-10]] — c3 → f3
- [[2026-02-19-warn-assets-s2-10]] — c2 → f2
- [[2026-02-19-fail-research-s1-10]] — c1 → f1
- [[2026-02-19-fail-assets-s3-9]] — c3 → f3
- [[2026-02-19-warn-assets-s2-9]] — c2 → f2
- [[2026-02-19-fail-research-s1-9]] — c1 → f1
- [[2026-02-19-fail-assets-s3-8]] — c3 → f3
- [[2026-02-19-warn-assets-s2-8]] — c2 → f2
- [[2026-02-19-fail-research-s1-8]] — c1 → f1
- [[2026-02-19-warn-tts-audio-clipping-2]] — Volume too high → Reduced volume by 3dB
- [[2026-02-19-fail-assets-image-hallucination-2]] — Changed reference angle → Reverted to original angle
- [[2026-02-19-fail-research-test-8]] — cause → fix
- [[2026-02-19-warn-dzine-phone-ghost-in-bg-remove-2]] — Ref had phone → Used drawbox to blank phone area
- [[2026-02-19-info-research-symptom-2-2]] — cause → fix
- [[2026-02-19-info-research-symptom-1-2]] — cause → fix
- [[2026-02-19-info-research-symptom-0-2]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-3]] — No price validation → Added price anomaly check
- [[2026-02-19-fail-research-test-7]] — cause → fix
- [[2026-02-19-fail-research-test-6]] — cause → fix
- [[2026-02-19-fail-research-test-5]] — cause → fix
- [[2026-02-19-fail-research-test-4]] — cause → fix
- [[2026-02-19-fail-research-test-3]] — cause → fix
- [[2026-02-19-fail-research-test-2]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories-2]] — No price validation → Added price anomaly check
- [[2026-02-19-fail-assets-s3-7]] — c3 → f3
- [[2026-02-19-warn-assets-s2-7]] — c2 → f2
- [[2026-02-19-fail-research-s1-7]] — c1 → f1
- [[2026-02-19-fail-assets-s3-6]] — c3 → f3
- [[2026-02-19-warn-assets-s2-6]] — c2 → f2
- [[2026-02-19-fail-research-s1-6]] — c1 → f1
- [[2026-02-19-fail-assets-s3-5]] — c3 → f3
- [[2026-02-19-warn-assets-s2-5]] — c2 → f2
- [[2026-02-19-fail-research-s1-5]] — c1 → f1
- [[2026-02-19-fail-assets-s3-4]] — c3 → f3
- [[2026-02-19-warn-assets-s2-4]] — c2 → f2
- [[2026-02-19-fail-research-s1-4]] — c1 → f1
- [[2026-02-19-fail-assets-s3-3]] — c3 → f3
- [[2026-02-19-warn-assets-s2-3]] — c2 → f2
- [[2026-02-19-fail-research-s1-3]] — c1 → f1
- [[2026-02-19-fail-assets-s3-2]] — c3 → f3
- [[2026-02-19-warn-assets-s2-2]] — c2 → f2
- [[2026-02-19-fail-research-s1-2]] — c1 → f1
- [[2026-02-19-fail-assets-s3]] — c3 → f3
- [[2026-02-19-warn-assets-s2]] — c2 → f2
- [[2026-02-19-fail-research-s1]] — c1 → f1
- [[2026-02-19-warn-tts-audio-clipping]] — Volume too high → Reduced volume by 3dB
- [[2026-02-19-fail-assets-image-hallucination]] — Changed reference angle → Reverted to original angle
- [[2026-02-19-fail-research-test]] — cause → fix
- [[2026-02-19-warn-dzine-phone-ghost-in-bg-remove]] — Ref had phone → Used drawbox to blank phone area
- [[2026-02-19-info-research-symptom-2]] — cause → fix
- [[2026-02-19-info-research-symptom-1]] — cause → fix
- [[2026-02-19-info-research-symptom-0]] — cause → fix
- [[2026-02-19-fail-research-asin-is-accessories]] — No price validation → Added price anomaly check
- [[2026-02-19-warn-research-test-symptom]] — test cause → test fix
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-fail-assets-product-image-hallucinated]] — Changed reference angle → Keep original angle
- [[2026-02-19-fail-assets-dzine-phone-ghost-in-bg]] — Amazon ref had phone, BG Remove missed it → Added drawbox white-out before BG Remove
- [[2026-02-19-fail-research-asin-b0f8hm4pyl-was-accessories-not-vacuum]] — No price validation against median → Added price anomaly check (<30% median)
- [[2026-02-19-v038-asin-accessories-detected-by-price-anomaly]] — ASIN B0F8HM4PYL (Narwal Freo Pro) was actually replacement accessories at $26.59 instead of the vacuum at $400+. New validation catches price <30% of category median.
- [[2026-02-19-pipeline-run-test-summary]] — Run test-summary: 5 generated, avg fidelity 9.5, avg variety 8.0
- [[2026-02-19-duplicate-title-3]] — Entry 2
- [[2026-02-19-duplicate-title-2]] — Entry 1
- [[2026-02-19-duplicate-title]] — Entry 0
- [[2026-02-19-test-learning]] — This is a test learning entry
- [[2026-02-19-script-quality-rules]] — **MANDATORY**: Script quality standards, feedback loop protocol, and text generation rules. Check BEFORE every script generation.
- [[2026-02-19-image-qa-rules]] — **MANDATORY**: Pre-generation ref checks + post-generation QA (phone ghosts, ghosting, color fidelity, white-on-white). Check BEFORE every run.
- [[2026-02-19-bg-remove-prerequisite]] — Product Background requires empty BG. Must run BG Remove first or get "Background is NOT empty" error.
- [[2026-02-19-identical-images]] — **CRITICAL**: Generative Expand ignores scene prompts. All 18 images came out identical. Switch to Product Background.
- [[2026-02-19-phone-removal]] — BG Remove treats phones as foreground. Must crop from reference before upload.
- [[2026-02-19-duplicate-dock]] — Tapo RV30 Expand created phantom second dock. Fixed with clean alternate Amazon image.
- [[2026-02-19-playwright-crash]] — Playwright "Sync API inside asyncio loop" when creating new instance per call. Fixed with shared session pattern.

## Patterns

### Recurring Theme: Tool Mismatch

Multiple failures trace to using the wrong Dzine tool:

- Generative Expand for scene variation (should use Product Background)
- Img2Img for faithful reproduction (should use BG Remove + scene tool)

### Recurring Theme: Reference Image Quality

Bad reference images cascade into bad outputs:

- Phones in reference → phones in output ([[2026-02-19-phone-removal]])
- Complex backgrounds → artifacts in expand ([[2026-02-19-duplicate-dock]])

### Recurring Theme: Quality Over Speed

- Refine scripts until authentic — no limit on passes
- Redo images if not video-ready — agents have vision QA now
- Save ALL feedback as learnings — text, image, audio, video

## Statistics

| Date       | Video    | Generated | Failed | Tool               | Key Issue                           |
| ---------- | -------- | --------- | ------ | ------------------ | ----------------------------------- |
| 2026-02-19 | vtest-qa | 18/18     | 0      | BG Remove + ProdBG | Minor: 01_mood phone, 04_hero ghost |
| 2026-02-19 | vtest-qa | 18/18     | 0      | Gen Expand (old)   | Identical backgrounds (FIXED)       |
```
