# DaVinci MCP Safe Profile (OpenClaw)

Last updated: 2026-02-09

## Goal

Automate one long YouTube video/day with low break risk in DaVinci Studio.

## GitHub Evidence Used

Primary references:

- `samuelgursky/davinci-resolve-mcp`
- `apvlv/davinci-resolve-mcp`
- `nobphotographr/davinci-resolve-automation`

Important finding:

- In `samuelgursky` feature matrix, many tools are implemented but only a small subset is verified on macOS.
- Keep autonomous usage limited to stable core operations.

## Production Tool Tiers

Tier A (allowed for autonomous runs):

- `get_current_page`
- `switch_page`
- `list_projects`
- `open_project`
- `save_project`
- `list_timelines_tool`
- `set_current_timeline`
- `import_media`
- `list_media_pool_clips`
- `create_bin`
- `move_media_to_bin`
- `add_clip_to_timeline`
- `clear_render_queue`

Tier B (manual-confirmation only, not autonomous by default):

- `create_project`
- `create_empty_timeline`
- `add_marker`
- `set_project_setting`
- `set_timeline_item_transform`
- `set_timeline_item_crop`
- `set_timeline_item_audio`
- `add_to_render_queue`
- `start_render`

Reason:

- These operations are useful but less consistently verified in public MCP testing.

## Denylist (Never Autonomous)

Never run without explicit Ray approval:

- `quit_app`
- `restart_app`
- any cloud mutation tool
- any account/user mutation tool
- any raw code execution tool (`execute_python`, `execute_lua`, equivalents)

## Studio + API Requirement

This profile assumes DaVinci Resolve Studio with external scripting enabled.
If scripting is not available, use manual editing and only generate runbooks.

## Required Preflight (Every Episode)

1. Run `/Users/ray/Documents/Rayviews/tools/davinci_smoke_test.py`.
2. Confirm script API connection is `ok: true`.
3. Confirm required episode files exist:

- `script_long.md`
- `seo_package.md`
- `edit_strategy.md`
- `video_safe_manifest.md`

4. Confirm ElevenLabs voiceover report exists and has no clipped chunks.

If any check fails, block DaVinci automation and write a blocker file.

## Daily Execution Flow (1 Long Video)

1. Planning:

- generate `davinci_edit_plan.md`
- generate `davinci_timeline_map.md`

2. Assembly:

- import media and voiceover
- place clips per timeline map

3. Audio:

- speech-first leveling
- reject clipped or noisy chunks

4. Export prep:

- generate `davinci_export_preset.md`
- generate `davinci_qc_checklist.md`

5. Handoff:

- produce uploader-ready package
- never auto-publish without Ray approval

## Fallback Strategy

If MCP becomes unstable, keep editing runbook mode active and use official Resolve API scripts (non-MCP) for targeted operations only.
Reference: `nobphotographr/davinci-resolve-automation` patterns for robust script-based helpers.

## Hard Gates

- Hook clarity in first 30 seconds.
- Visual cadence mostly 2-4 seconds.
- Speech intelligibility end-to-end.
- No clipped peaks in final mix.
- Dynamic metrics include "at time of recording".
- Affiliate and AI disclosures are present.

## Failure Policy

If any hard gate fails:

1. Mark `NO-GO`.
2. Write exact blocker + next action in episode folder.
3. Stop before upload.
