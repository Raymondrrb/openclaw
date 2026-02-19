# Dzine Operator Manual (Living Document)

Last updated: 2026-02-09
Owner: dzine_producer + dzine_researcher

## Purpose

Standardize how Ray's team uses Dzine for daily Amazon review videos with one stable avatar identity.

## Identity Lock

- Character tab: always select `Ray`.
- Face identity: fixed across all episodes.
- Outfit: may vary by episode.
- Voice: fixed ElevenLabs voice profile.

## Character Prompt System (Insert Character)

In Dzine "Insert Character", always fill both prompt boxes with role separation:

1. Character description (top box):

- Keep fixed identity anchor for Ray (facial traits, age range, lens/look style, channel visual language).
- Allow outfit variation by product category/day.
- Keep coherence with channel identity (no random style shifts).

2. Character action & scene (bottom box):

- Describe a scene directly relevant to products being reviewed that day.
- Place Ray in context with the product use case.
- Prefer natural product presence in scene (in-hand/on-desk/in-environment), not floating object collage.
- Keep each scene brief and editable for short lip-sync inserts (intro/bridges/outro CTA).

## Preflight Check (Before Any Heavy Run)

1. Confirm current plan capacity (video credits, concurrent video jobs, upscale ceiling).
2. Confirm enough credits for full episode + retries.
3. Confirm target export requirement (minimum 1080p for main channel workflow).
4. Confirm session is logged in and generation queue is responsive.

Confidence: **Medium** (based on official pricing/capability pages that can change over time).

## Episode Eligibility Gate (Before Opening Dzine)

Only start Dzine generation when all gates below are true:

1. `script_long.md` exists for the target episode.
2. `quality_gate.md` exists and explicitly states `Decision: PASS`.
3. `dispatch_brief.md` has concrete product targets (not `N/A` placeholders for product/price/rating).

If any gate fails:

- Mark status as `BLOCKED (PRE-FLIGHT)`.
- Do not spend Dzine credits.
- Write blocker and recovery steps in daily Dzine blocker report.

Confidence: **High** for gate utility (observed on 2026-02-09 content audit); **Medium** for long-term false-positive rate (needs more cycles).

## Lip Sync Mode Selection

- **Single-face scenes (default):** Use standard Lip Sync workflow.
- **2–4 speaker/group scenes:** Use Multi-Character Lip Sync workflow.
- Keep `Character = Ray` for all Ray-led scenes; for multi-face scenes, define speaker-face mapping before generate.

Confidence: **Medium** (official Dzine tool pages claim up to 4-face support; internal stress tests still limited).

## Recommended Daily Flow

1. Open Dzine in the OpenClaw managed browser session (logged in).
2. Create New Project.
3. Set Character tab to `Ray` before each generation run.
4. Choose lip sync mode (single vs multi-character) based on scene design.
5. Import scene-specific voice chunk (45–90s default).
6. Optional long-form mode: use longer dialogue clips only when continuity outweighs retake control (official claim supports up to 5-minute dialogue; validate per project).
7. Set highest quality mode available and target 1080p minimum.
8. Generate and review movement quality (speech transitions + idle micro-motion).
9. Build product visuals from reference:

- use Amazon images as reference input only,
- run img2img in Dzine (NanoBanana Pro) for original variants,
- keep best variants with high product fidelity.

10. Generate product-in-hand scenes using selected variants.
11. Generate 3–5 thumbnail variants for A/B selection.
12. Export assets and log every output in manifest.

## Video Composition Ratio

Default editorial mix for long videos:

- 80-90% narrated product/environment visuals.
- 10-20% avatar lip-sync inserts (Ray).

Lip-sync is for strategic presence, not full talking-head.

## Lip Sync Placement Standard

For each episode, define a placement map:

- Intro: 6-12s avatar segment.
- Mid-video: 1-2 short inserts (4-8s each) near key transitions.
- Outro CTA: optional 4-8s.

Create and store: `dzine_lipsync_map.md`.

## Quality Criteria

- Lip sync smooth between phrases (no freeze effect).
- Background motion coherent and stable.
- Product visibility clear in first 2 seconds of product scenes.
- Text-safe composition (space for captions and callouts).
- Disclosure scene included when required.

## Product Fidelity Gate (Required for Amazon Review Content)

Reject or regenerate if any of the following fail:

1. Product silhouette/proportions mismatch reference.
2. Buttons/ports/controls are misplaced.
3. Logo/branding placement is inconsistent.
4. Stylization makes product identity ambiguous.
5. Visual artifacts suggest unusable fake render (warped edges/invalid geometry).

Confidence: **High** for requirement relevance; **Medium** for Dzine-specific pass-rate consistency (needs more benchmark data).

## Known Tradeoffs

- Dzine: often smoother movement and better cinematic background behavior.
- HeyGen: broader feature set for subtitles/motion controls in-app.
- Channel default: Dzine primary. Escalate to HeyGen only if a required feature is missing.

## Blockers and Recovery

- Managed session not authenticated:
  - Open Dzine login page in OpenClaw managed browser and complete login.
- Session/login/captcha expired:
  - Complete manually and keep tab open.
- Export disabled:
  1. Click generated item in Results.
  2. Open Image Editor/canvas.
  3. Ensure generated result is active as a layer.
  4. Re-check Export button.
  5. If still disabled, refresh once and reopen project result.

Confidence on export recovery: **High** (observed in real run on 2026-02-07).

## Asset Status Semantics (use in manifest)

- `GENERATED_IN_APP`: preview exists in Dzine results, but file not exported yet.
- `EXPORTED`: file saved and path verified in project folder.
- `PENDING`: not generated.
- `BLOCKED`: generation/export cannot proceed due to platform/session issue.

Rule: do **not** mark episode visual production complete while critical scenes remain `GENERATED_IN_APP` without exported files.

Confidence: **High** (observed in episode `auto_airpods_pro_3_vs_bose_qc_ultra_2nd_gen_which_250_2026-02-07`, where S01 was generated but pipeline was still blocked).

## Export Blocker Escalation Threshold

If Export remains disabled after the standard recovery sequence + one refresh cycle:

1. Mark affected scene as `BLOCKED`.
2. Log exact blocker steps in `dzine_blockers.md`.
3. Continue documentation work (prompt pack/manifest/thumbnails) but declare runtime status as **PARTIAL COMPLETE**.
4. Do not queue additional heavy generations until export path is restored.

Confidence: **High** (matches latest in-app behavior and prevented additional wasted runs on 2026-02-07).

## Episode Readiness/Handoff Gate

Before an episode can move from planning to visual production complete, verify all required Dzine outputs exist in `content/<episode>/`:

1. `dzine_prompt_pack.md`
2. `dzine_asset_manifest.md`
3. `dzine_generation_report.md`
4. `dzine_thumbnail_candidates.md`

If only `dzine_producer_task.md` exists and none of the four output files were created, status must be `NOT_STARTED` (not partial-complete).

Confidence: **High** (observed in `auto_opportunity_2026-02-08`, where task file exists but no Dzine output package yet).

## Required Outputs Per Episode

- dzine_prompt_pack.md
- dzine_asset_manifest.md
- dzine_generation_report.md
- dzine_thumbnail_candidates.md
- dzine_lipsync_map.md
- dzine_img2img_plan.md
