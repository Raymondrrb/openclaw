# DaVinci Operator Manual (Living Document)

Last updated: 2026-02-08
Owner: davinci_editor + davinci_researcher

## Purpose

Standardize how Ray's team edits Amazon review videos in DaVinci Resolve for repeatable quality and monetization readiness.

## Workflow Scope

- Long videos: 8-12 min, 16:9.
- Shorts: 9:16 cutdowns from long master.
- Inputs: script, Dzine assets, ElevenLabs voice, SEO package.

## Project Baseline

- Timeline: 1920x1080 (or 3840x2160 if source supports) at 30 fps.
- Audio sample rate: 48 kHz.
- Color: keep consistent project-level color management per channel.
- Naming pattern: `<slug>_vXX`.

## Edit Structure (Long Video)

1. Hook (0-30s): promise + visual contrast + category context.
2. Criteria setup.
3. Ranked sections (one clear point per visual block).
4. Verdict + CTA.
5. Disclosures and compliance check.

## Workflow Stage Gates (Resolve Page Order)

Use a strict page-gated sequence for predictable delivery:

1. **Media**: ingest, organize bins, verify frame rate/audio sample rate.
2. **Edit**: narrative assembly and primary story decisions.
3. **Cut**: speed-pass trims and rhythm tightening when iteration speed matters.
4. **Fusion**: only required graphics/VFX shots (avoid unnecessary complexity on review videos).
5. **Color**: consistency pass after picture lock.
6. **Fairlight**: speech-first mix and loudness compliance.
7. **Deliver**: preset-driven export + QC validation.

Gate rule: avoid mixing heavy color/audio decisions before picture lock unless blocker-level issues appear.
Timeline rule: the Edit/Cut timeline is the source of truth for Fusion/Color/Fairlight/Deliver decisions.

## Media Prep and Organization Rules

- Build bins before heavy editing; use metadata/keywords for retrieval.
- Ensure clips are truly imported into project media pool (not only browsed).
- Use AutoSync Audio for dual-system recordings when applicable.
- After sync, verify mapped audio and flag unmatched clips before story assembly.

## Track Layout Standard

- V1: base scene footage/avatar
- V2: product overlays/B-roll
- V3: text/callouts/captions
- A1: primary VO (ElevenLabs)
- A2: background music
- A3: SFX

## Audio Chain Standard (Fairlight)

- Prioritize speech intelligibility over music impact.
- **Pre-Fairlight VO ingest gate (hard):**
  - Reject/repair any narration chunk with peak higher than **-1.0 dB** in source QC reports.
  - If flagged, route to normalize/re-render path before final mix timeline lock.
  - Keep a `*_do_not_use_clipped` or equivalent quarantine folder for unsafe takes.
- **Resolve 20 recommended two-stage flow (if available):**
  1. AI Audio Assistant for fast first-pass balance,
  2. Dialogue Separator FX to rebalance voice/background/ambience,
  3. Ducker Track FX to auto-lower music under speech,
  4. 6-band clip EQ + gentle compression for tonal control,
  5. De-esser if needed,
  6. Limiter safety.
- **Fallback (non-Resolve-20 / conservative mode):**
  1. High-pass filter (light)
  2. Gentle compression
  3. De-esser if needed
  4. Limiter safety
- Music under VO: low enough to avoid masking key words.
- Target loudness: around -14 LUFS integrated for YouTube delivery.
- Rule: AI pass is assistive only; final intelligibility sign-off is human.

## Visual Pace Rules

- Visual change every ~2-4s when explaining comparisons.
- Use **chapter-like block structure** in long edits (hook → criteria → ranked items → verdict) and tighten pacing at each block boundary.
- For music-backed sections, run **AI Detect Music Beats** first and use beat markers as candidate cut anchors.
- Avoid unnecessary transitions; use cuts for speed and clarity.
- Keep safe margins for mobile crop and captions.
- Product shot should be clearly visible in first 2s of each product segment.
- Cadence QC: ensure no segment exceeds ~5s without visual update unless intentionally used for emphasis.

## Edit Discipline Rules

- Build structure first, polish second: Hook → Criteria → Ranked sections → Verdict.
- Use in/out selection before insertion when source clips are long and noisy.
- Use append/insert for rough assembly, then refinement trim pass.
- Remove unnecessary split points with **Delete Through Edit** before color pass.
- Use Cut page for speed roughing/multicam; use Edit page for precision audio-sensitive refinement.

## Resolve 20 Speed-Safety Additions (Operational)

- During rough trims on Cut page, enable **Safe Trimming Mode** to reduce accidental overwrite risk while tightening rhythm.
- Use Voice Over Palette/Tool for short pickup fixes directly in timeline when faster than full external re-render.
- If VO pickup is recorded in-app, place it on a dedicated pickup track first, then comp/replace on A1 only after intelligibility check.
- AI-assisted tools (Audio Assistant, subtitle animation, etc.) are acceleration layers, not final authority.

## Compliance Rules

- Ensure affiliate disclosure and AI disclosure are present in metadata package.
- For dynamic metrics (price/rating), include "at time of recording".
- No unsupported medical/financial/legal claims.

## Export Profiles

- Long master: H.264/H.265 high quality, 16:9.
- Shorts: reframed 9:16 versions with readable caption placement.
- Final check before export: no clipped audio, no black frames, no broken caption timing.

## Dynamic Metrics Freshness Gate (Publish Reliability)

- At **T-30 minutes before export/publish**, refresh dynamic values (price/rating/review count) from current source of truth.
- On-screen dynamic cards must keep the phrase: **at time of recording**.
- **Metric-card parity check (hard):** refreshed values in notes/SEO must match all on-screen overlays before final render.
- Record verification timestamp in upload packet/checklist.
- If refreshed numbers change meaningfully, re-open affected graphic/text shots before final render.

## Shorts (9:16) QC Micro-Checklist

- First 2 seconds: product/subject legible and centered for mobile viewing.
- Subtitles/callouts do not collide with UI-sensitive zones.
- Essential comparison text stays readable on small screens.
- Reframe avoids cutting off hands/product edges during key demonstrations.

## Proxy and Relink Reliability Protocol

1. Edit phase: proxy mode allowed/preferred for responsiveness.
2. Finishing phase: relink to camera originals before final color/audio sign-off.
3. Pre-export validation pass:
   - no offline media
   - no clipped audio peaks on master
   - no unintended black frames
   - captions timing and safe-area review
4. Export after validation only.
5. If export fails, use retry ladder in order:
   - preserve error/log notes,
   - verify relink status (originals online),
   - clear/refresh problematic render cache segments,
   - retry same preset,
   - only then escalate to alternate codec/container test render.

## Blockers and Recovery

- Missing required assets:
  - Regenerate from upstream agent outputs before timeline lock.
- Audio artifacts in VO:
  - Re-render affected ElevenLabs segment only; replace on A1.
  - Quick triage order: (1) swap to normalized variant, (2) clip gain trim, (3) de-esser/EQ touch-up, (4) segment re-render.
- Inconsistent color/look:
  - Apply unified correction pass and compare against channel baseline.
- Render instability:
  - Use cache/proxy workflow and re-export.

## Required Outputs Per Episode

- davinci_edit_plan.md
- davinci_timeline_map.md
- davinci_export_preset.md
- davinci_qc_checklist.md

## Confidence Levels (Current)

- Stage-gated workflow order: **High**
- Media prep + AutoSync discipline: **High**
- Edit/Cut role separation and refinement flow: **High**
- Fusion node discipline for practical use: **High**
- Color node-order workflow: **Medium-High**
- Fairlight chain + VO ingest peak gate: **Medium-High**
- Deliver reliability protocol (proxy/relink + retry ladder): **Medium-High**

## Evidence References

- Blackmagic Design — DaVinci Resolve What's New (Resolve 20):
  https://www.blackmagicdesign.com/products/davinciresolve/whatsnew
- Ground Control (YouTube) — Introduction to DaVinci Resolve [Full Course] (2026):
  https://www.youtube.com/watch?v=MCDVcQIA3UM
- Transcript focus used for operational extraction:
  /Users/ray/Documents/Rayviews/reports/davinci/video_MCDVcQIA3UM_transcript_focus.txt

## MCP Integration Baseline (OpenClaw)

- Primary MCP reference: `samuelgursky/davinci-resolve-mcp`.
- Production must run with constrained tool allowlist only.
- Do not run shutdown/cloud/admin/raw-code tools autonomously.
- Enforce profile in:
  `/Users/ray/Documents/Rayviews/agents/workflows/davinci_mcp_safe_profile.md`

### Daily Throughput Target

- Initial mode: `1` long video/day with quality-first gating.
- Scale only after repeated GO runs with no safety or QC regressions.
