# Workflow: Dzine Producer

Goal: generate daily avatar+product scenes in Dzine for the selected Amazon US episode.

## Inputs

- `content/<slug>/script_long.md`
- `content/<slug>/shot_list.md` (if available)
- `content/<slug>/asset_manifest.md` (if available)
- `content/<slug>/video_safe_manifest.md` (if available)
- `content/<slug>/quality_gate.md`
- `content/<slug>/elevenlabs_voiceover_report.md` (preferred)

## Outputs

- `content/<slug>/dzine_prompt_pack.md`
- `content/<slug>/dzine_asset_manifest.md`
- `content/<slug>/dzine_generation_report.md`
- `content/<slug>/dzine_thumbnail_candidates.md`
- `content/<slug>/dzine_lipsync_map.md`
- `content/<slug>/dzine_img2img_plan.md`

## Standard scene set

1. Hook avatar scene (0-20s)
2. Criteria scene
3. One product scene per ranked item
4. Pros/cons card scenes
5. Final verdict + CTA scene
6. Thumbnail A/B set (3-5 options)

## Editorial ratio (must follow)

- Most of the video should be narration + visuals.
- Target ratio:
  - 80-90% product/environment visuals (stills/motion from Dzine).
  - 10-20% avatar lip-sync segments with `Ray`.
- Avoid continuous talking-head timeline.

## Avatar consistency policy

- In Dzine Character tab, select `Ray` for all scenes.
- Keep same face identity every day.
- Outfit may change daily.
- Keep framing and lighting consistent.

## Insert Character protocol (mandatory)

In Dzine "Insert Character":

1. Character description (top field):

- Keep a fixed identity anchor for Ray (face, age range, hair, tone, lens style, channel visual language).
- Change outfit daily according to product category, but keep overall channel coherence.

2. Character action & scene (bottom field):

- Place Ray in a scene relevant to the products of the day.
- Include product context in environment (desk setup, travel setup, gym setup, home office, etc.).
- When relevant, include products in-hand or positioned naturally in scene composition.

## Browser execution policy

- Preferred: OpenClaw managed browser session with logged-in Dzine account.
- Keep this managed session persistent to avoid repeated auth/captcha prompts.
- If session invalid: report blocker and stop; do not fake completion.

## Execution protocol (from benchmark learning)

1. Create project in Dzine and use **Lip Sync** workflow.
2. Lock character identity:
   - Character tab -> select `Ray`.
3. Fill Insert Character fields explicitly for each avatar scene:
   - Top field (character description): fixed Ray identity anchor + episode-specific outfit.
   - Bottom field (character action & scene): product-relevant setting + natural product placement.
4. Use final voice chunks (ElevenLabs) per scene.
5. Select highest quality mode available and target 1080p output.
6. Product visuals with originality:
   - Use Amazon product image only as reference input.
   - After capturing each reference, close the Amazon product tab to keep browser state clean.
   - Run Dzine `img2img` with NanoBanana Pro to generate original variants.
   - Generate at least 3 approved images per ranked product (minimum 15 images for Top 5).
   - Do NOT render price inside Dzine images.
     - Leave clean negative space (top-left or bottom-left) for a DaVinci price overlay template fed from `product_selection.json`.
   - Keep only high-fidelity outputs.
7. For product-in-hand scenes:
   - attach/reference product image and enforce similarity without copying exact page screenshot look.
8. For style consistency:
   - use one reference image for background/look when needed.
9. Validate smoothing quality:
   - no hard freeze between phrases,
   - subtle idle movement,
   - stable background motion.
10. Generate 3-5 thumbnail variants and score for CTR basics.

## Lip Sync placement map

Create `dzine_lipsync_map.md` with recommended insertion points:

- Intro segment: 6-12s (high priority).
- Mid-video bridge: 1-2 short segments (4-8s each).
- Optional outro CTA: 4-8s.
- Keep lip-sync clips short and high-impact; do not exceed target avatar ratio.

## Image generation plan

Create `dzine_img2img_plan.md` containing:

- Product reference source (Amazon URL/image)
- Prompt objective per product
- Style constraints (coherent with channel look)
- Variant shortlist and selected outputs
- Rejected outputs with reason

## Hard gates

- Require `quality_gate.md` PASS before final generation.
- Require explicit note for affiliate + AI disclosure placement.
- Add "at time of recording" note for dynamic metrics scenes.
- Fail if any ranked product has fewer than 3 approved visuals.
- Reject low-quality frames, off-model avatar identity, and distorted product shapes.
- Do not use raw full-page Amazon screenshots as final visual assets.
