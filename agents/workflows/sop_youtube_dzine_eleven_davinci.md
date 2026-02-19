# SOP: YouTube Reviews (Dzine + ElevenLabs + DaVinci)

Goal: publish high-quality Amazon US review videos (Top 3/Top 5) with consistent quality, compliance, and repeatable throughput.

Audience rules:

- Chat language with Ray: Portuguese.
- Deliverables: English.
- Always include affiliate disclosure + AI disclosure.
- Treat price/rating as dynamic; include "at time of recording".

## 1) Daily Run Order

1. Market scan and opportunity pick.
2. Research pack + affiliate links.
3. Script long-form + SEO package.
4. Review + edit strategy + quality gate.
5. Visual asset plan + Dzine generation.
6. ElevenLabs voiceover.
7. DaVinci API preflight (smoke test).
8. DaVinci assembly and polish.
9. Publisher pack + upload payload draft.
10. Final publish checklist + upload.

## 2) Core Paths

- Base workspace: `/Users/ray/Documents/Rayviews`
- Episode folder pattern: `/Users/ray/Documents/Rayviews/content/<episode_slug>/`
- Agent workflow docs: `/Users/ray/Documents/Rayviews/agents/workflows/`

## 3) Agent Pipeline Commands

Replace `<EPISODE_DIR>` with today folder.

```bash
openclaw agent --agent researcher --message "Read <EPISODE_DIR>/dispatch_brief.md and /Users/ray/Documents/Rayviews/agents/workflows/affiliate_linker_playbook.md. Keep one category of the day only. Build deep Top 5 with Amazon metrics + at least 2 trusted external sources per product, then create BOTH files: <EPISODE_DIR>/research.md and <EPISODE_DIR>/affiliate_links.md. For affiliate, use OpenClaw managed browser, click yellow SiteStripe 'Get link', capture popup URL with tag=, then close product tab. If blocked, write blocker details and stop."
```

```bash
openclaw agent --agent scriptwriter --message "Read <EPISODE_DIR>/dispatch_brief.md, <EPISODE_DIR>/research.md and <EPISODE_DIR>/affiliate_links.md. Create BOTH files: <EPISODE_DIR>/script_long.md and <EPISODE_DIR>/seo_package.md. Script must be human-authentic (no AI-generic tone), evidence-driven, and 8-12 min narration."
```

```bash
openclaw agent --agent reviewer --message "Review <EPISODE_DIR>/research.md, <EPISODE_DIR>/script_long.md, <EPISODE_DIR>/seo_package.md. Create THREE files: <EPISODE_DIR>/review_final.md, <EPISODE_DIR>/edit_strategy.md, <EPISODE_DIR>/quality_gate.md."
```

```bash
openclaw agent --agent dzine_producer --message "Read <EPISODE_DIR>/script_long.md, <EPISODE_DIR>/edit_strategy.md, <EPISODE_DIR>/video_safe_manifest.md and /Users/ray/Documents/Rayviews/agents/workflows/dzine_producer_playbook.md. Use OpenClaw managed browser session for Dzine. Generate at least 3 approved original images per ranked product using img2img + NanoBanana Pro; do NOT render price in Dzine, leave negative space for a DaVinci overlay template. Create shot_list.md, asset_manifest.md, dzine_prompt_pack.md, dzine_asset_manifest.md, dzine_generation_report.md, dzine_thumbnail_candidates.md, dzine_lipsync_map.md, dzine_img2img_plan.md in <EPISODE_DIR>. If blocked by auth/captcha, write blockers and stop."
```

```bash
openclaw agent --agent davinci_editor --message "Read <EPISODE_DIR>/script_long.md, <EPISODE_DIR>/seo_package.md, <EPISODE_DIR>/edit_strategy.md, <EPISODE_DIR>/video_safe_manifest.md and /Users/ray/Documents/Rayviews/agents/workflows/davinci_editor_playbook.md. Create davinci_edit_plan.md, davinci_timeline_map.md, davinci_export_preset.md, davinci_qc_checklist.md inside <EPISODE_DIR>."
```

```bash
openclaw agent --agent publisher --message "Read <EPISODE_DIR>/affiliate_links.md, <EPISODE_DIR>/seo_package.md, <EPISODE_DIR>/review_final.md, <EPISODE_DIR>/quality_gate.md, <EPISODE_DIR>/davinci_qc_checklist.md and /Users/ray/Documents/Rayviews/agents/workflows/publisher_playbook.md. Create publish_package.md, upload_checklist.md, youtube_studio_steps.md, youtube_upload_payload.md, youtube_upload_checklist.md, youtube_publish_hold.md inside <EPISODE_DIR>. Stop before final publish click and require Ray approval."
```

## 4) Dzine Prompt Template (Avatar + Product Scenes)

Use this in Dzine after script is approved.

```text
Create a 16:9 YouTube review visual package for this script.
Style: clean tech, premium, factual, no exaggerated claims.
Avatar: consistent host identity across all scenes.
Scene objectives:
1) Hook scene (0-20s) with product category promise.
2) Ranking intro scene with criteria text overlay.
3) One scene per ranked product with clear product visual focus.
4) Pros/cons visual cards for each product.
5) Final verdict scene + CTA.
Requirements:
- Keep composition readable for captions.
- Avoid copyrighted logos unless in factual review context.
- Export scene IDs matching script sections.
- No medical/financial claims.
```

## 5) ElevenLabs Prompt/Settings Template

Voice target:

- Voice profile: `Ray` (mandatory).
- Neutral US English.
- Confident, practical, no hype tone.

Generation instructions:

```text
Narrate this script in clear US English for a product comparison video.
Pace: medium-fast.
Energy: controlled.
Style: trustworthy reviewer, concise delivery.
Pause briefly before each ranked product and before CTA.
```

Recommended workflow:

- Generate in chunks of 45-90 seconds.
- File naming: `vo_01_hook.wav`, `vo_02_criteria.wav`, ...
- Keep one fixed model + settings preset for all episodes (consistency).
- Re-generate only faulty chunks.

## 6) DaVinci Execution Standard

Project baseline:

- Timeline: 3840x2160 or 1920x1080 (keep consistent per channel).
- FPS: 30.
- Audio sample rate: 48 kHz.

Track layout:

- V1: main scenes
- V2: product overlays and cut-ins
- V3: text/captions
- A1: ElevenLabs VO
- A2: music bed
- A3: SFX

Audio targets:

- VO integrated loudness near -14 LUFS for YouTube.
- Keep music low enough to preserve speech clarity.

Exports:

- Long: 16:9 H.264/H.265 master.
- Shorts: 9:16 reframed cutdowns.

Preflight before edit:

- Run `/Users/ray/Documents/Rayviews/tools/davinci_smoke_test.py`.
- Continue only when `tmp/davinci_smoke/smoke_report.json` has `ok: true`.

## 7) Quality Gate (Must Pass)

1. Every fact in script maps to a source link in `research.md`.
2. Dynamic metrics include "at time of recording".
3. Affiliate disclosure present in description and pinned comment.
4. AI disclosure present in description.
5. No unsupported claims (health, financial, legal).
6. Visuals are licensed, original, or explicitly review-safe.
7. Voice is clear; no clipping; pronunciation reviewed for product names.
8. Hook promise matches actual content.
9. CTA appears naturally and once near the end plus optional light early tease.
10. Final QA file exists: `<EPISODE_DIR>/davinci_qc_checklist.md`.

## 8) Publish Checklist (Manual)

1. Upload final long video to YouTube Studio.
2. Paste SEO title/description/tags from `seo_package.md`.
3. Paste affiliate links from `affiliate_links.md` with disclosure.
4. Add AI disclosure line.
5. Add chapters and pinned comment.
6. Add thumbnail aligned with title promise.
7. Set end screen + cards.
8. Set schedule (preferred daily fixed slot).
9. After publish, log performance baseline at 1h/24h/72h.

## 9) Suggested Daily Cadence (America/Sao_Paulo)

- 09:00: trend + market scan.
- 10:00-13:00: research/script/seo/review.
- 14:00-18:00: Dzine + ElevenLabs + DaVinci edit.
- 19:00-20:00: QA + publish + metric log.

## 10) File-Driven Pipeline (Structured Mode)

Each step writes files. The next step reads them. No chained agents.

```
OpenClaw (decides video) → Script Agent → Assets Agent → Voice Agent → Edit Agent → Upload Agent → Metrics Agent → Supabase → Loop
```

### Architecture

```
pipeline_runs/{run_id}/
├── run.json                 ← Run metadata and state
├── product_selection.json   ← discover-products (market scout)
├── script.json              ← generate-script (structured script)
├── dzine_prompts.json       ← generate-assets (image prompts)
├── assets_manifest.json     ← generate-assets (image inventory)
├── assets/                  ← generate-assets (generated images)
├── voice_manifest.json      ← generate-voice (voice segments)
├── voice_segments/          ← generate-voice (text + audio per segment)
├── full_narration.txt       ← generate-voice (concatenated narration)
├── davinci/
│   └── project.json         ← build-davinci (DaVinci assembly plan)
├── rayvault/
│   └── publish/
│       └── video_final.mp4  ← render-and-upload (rendered video)
├── upload/
│   └── youtube_url.txt      ← render-and-upload (published URL)
└── metrics.json             ← collect-metrics (24h performance)
```

### Commands

```bash
# Check status
python3 tools/pipeline.py status --run-id RUN_ID

# Run end-to-end (stops at gates for approval)
python3 tools/pipeline.py run-e2e --category "desk_gadgets"

# Run individual steps
python3 tools/pipeline.py init-run --category "desk_gadgets"
python3 tools/pipeline.py discover-products --run-id RUN_ID
python3 tools/pipeline.py generate-script --run-id RUN_ID
python3 tools/pipeline.py approve-gate1 --run-id RUN_ID --reviewer Ray --notes "GO"
python3 tools/pipeline.py generate-assets --run-id RUN_ID
python3 tools/pipeline.py generate-voice --run-id RUN_ID
python3 tools/pipeline.py build-davinci --run-id RUN_ID
python3 tools/pipeline.py approve-gate2 --run-id RUN_ID --reviewer Ray --notes "GO"
python3 tools/pipeline.py render-and-upload --run-id RUN_ID
python3 tools/pipeline.py collect-metrics --run-id RUN_ID
```

### Safety rules

- Each step verifies previous files exist before running
- Never overwrites completed steps (idempotent)
- Stops pipeline on failure instead of proceeding with bad data

### Legacy dispatch (agent-chained mode)

```bash
python3 "/Users/ray/Documents/Rayviews/tools/market_auto_dispatch.py" --date TODAY --notify-agents --wait-seconds 120
```

If quality gate fails, fix script/facts first, then re-run only downstream steps.

## 11) OpenClaw Browser Mode (Logged Session Priority)

For Dzine/Amazon/YouTube operations, use OpenClaw managed browser sessions:

- Keep one persistent authenticated session for Amazon, Dzine, and YouTube Studio.
- Avoid dependency on browser relay extension for normal daily automation.
- If session expires, refresh login in managed browser and resume pipeline.

This avoids creating a fresh browser profile and reduces login/captcha friction.

## 12) Dzine Deep Study (Continuous Improvement)

```bash
openclaw agent --agent dzine_researcher --message "Run deep Dzine study using /Users/ray/Documents/Rayviews/agents/workflows/dzine_deep_study_playbook.md and update /Users/ray/Documents/Rayviews/agents/knowledge/dzine_operator_manual.md with evidence-based improvements."
```

## 13) DaVinci Deep Study (Continuous Improvement)

```bash
openclaw agent --agent davinci_researcher --message "Run deep DaVinci study using /Users/ray/Documents/Rayviews/agents/workflows/davinci_deep_study_playbook.md and update /Users/ray/Documents/Rayviews/agents/knowledge/davinci_operator_manual.md with evidence-based improvements."
```
