# Workflow: DaVinci Editor

Goal: convert episode package into an execution-ready DaVinci editing runbook for one long video/day.

## Inputs

- `content/<slug>/script_long.md`
- `content/<slug>/seo_package.md`
- `content/<slug>/edit_strategy.md`
- `content/<slug>/quality_gate.md` (if exists)
- `content/<slug>/video_safe_manifest.md`
- `content/<slug>/elevenlabs_voiceover_report.md` (preferred)
- `agents/knowledge/davinci_operator_manual.md`
- `agents/workflows/davinci_mcp_safe_profile.md`

## Outputs

- `content/<slug>/davinci_edit_plan.md`
- `content/<slug>/davinci_timeline_map.md`
- `content/<slug>/davinci_export_preset.md`
- `content/<slug>/davinci_qc_checklist.md`

## Required Sections

1. Project setup (fps, resolution, color management)
2. Timeline block map with timestamps
3. Track layout (VO, music, SFX, captions, overlays)
4. Scene-by-scene edit instructions
5. Audio chain settings and loudness target
6. Export settings for YouTube long + shorts
7. Final QC gate
8. Render risk checklist + fallback actions
9. MCP safety mapping (which allowed tool handles each stage)

## MCP Operation Rule

- If using MCP automation, operate only through the allowlist in `davinci_mcp_safe_profile.md`.
- Never use app shutdown, cloud mutation, or raw-code execution tools in autonomous mode.
- If a needed action is outside allowlist, stop and mark `REVIEW_REQUIRED`.

## Mandatory Preflight

Before generating `GO`-oriented editing docs:

1. Run `/Users/ray/Documents/Rayviews/tools/davinci_smoke_test.py`.
2. Read `tmp/davinci_smoke/smoke_report.json`.
3. If `ok != true`, output `NO-GO` and include exact blocker/recovery steps.
4. If voiceover report exists, reject segments with clipping warnings.

## Hard Gates

- Use only `assets/video_safe/*_16x9.jpg` when available.
- Ensure affiliate + AI disclosures exist before publish.
- Enforce `at time of recording` where dynamic pricing/rating appears.
- Enforce speech intelligibility and no clipped audio in final QC.
- If any hard gate fails, result must be `NO-GO`.
