# Claude Code Alignment Contract (RayViewsLab)

## Goal

Keep Codex + Claude Code working on the same project without drift.

## Source of truth

- Primary repo (default): `/Users/ray/Documents/Rayviews`
- Secondary repo (OpenClaw runtime only): `/Users/ray/Documents/openclaw`

## Hard boundary

1. If task is channel pipeline, Supabase/Vercel control-plane, content/gates, assets, voice, DaVinci orchestration:
   - Work ONLY in `/Users/ray/Documents/Rayviews`.
2. Touch `/Users/ray/Documents/openclaw` ONLY for OpenClaw runtime/gateway internals.
3. Never implement the same feature in both repos unless explicitly requested.

## Session start checklist (Claude must execute)

1. `pwd`
2. `git remote -v`
3. `git branch --show-current`
4. Confirm in one line: "Source of truth for this task: <repo>"
5. Read:
   - `/Users/ray/Documents/Rayviews/WORKSPACE_BOUNDARY.md`
   - `/Users/ray/Documents/Rayviews/tasks/lessons.md`

## OpenClaw safety (non-negotiable)

- Never create 1-second loops spawning `openclaw browser` repeatedly.
- Prefer one `openclaw browser wait --fn` with explicit timeout.
- Do not run parallel ChatGPT UI loops.
- If process pressure is high, run:
  - `tools/openclaw_recover.sh` (inspect)
  - `tools/openclaw_recover.sh --apply --restart-browser` (recover)

## Shared-file sync policy (only when needed)

From Rayviews repo:

- Dry run: `tools/sync_with_openclaw.sh --to-openclaw`
- Apply: `tools/sync_with_openclaw.sh --to-openclaw --apply`

Synced set:

- `tools/chatgpt_ui.py`
- `tests/test_chatgpt_ui.py`
- `tools/openclaw_recover.sh`

## Delivery protocol

- Before finalizing, Claude must provide:
  1. Changed file list
  2. Commands run
  3. Test results
  4. Any cross-repo sync performed
