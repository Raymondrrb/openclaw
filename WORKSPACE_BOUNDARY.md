# Workspace Boundary (RayViewsLab)

This project currently lives across **two local repos**:

- Channel Ops (this repo): `/Users/ray/Documents/Rayviews`
- OpenClaw runtime/fork: `/Users/ray/Documents/openclaw`

## Rule

For channel pipeline tasks, use this repo (`/Users/ray/Documents/Rayviews`) as canonical.
Only touch `/Users/ray/Documents/openclaw` when the task is explicitly about OpenClaw runtime/gateway internals.

## Why

Mixing both repos in one coding session causes drift, duplicated patches, and agent confusion.

## Controlled Sync

When a shared utility must be copied to the OpenClaw repo, use:

```bash
tools/sync_with_openclaw.sh --to-openclaw --apply
```

Dry-run first:

```bash
tools/sync_with_openclaw.sh --to-openclaw
```

Current synced set:

- `tools/chatgpt_ui.py`
- `tests/test_chatgpt_ui.py`
- `tools/openclaw_recover.sh`

Operational handoff for Claude Code:

- `tasks/CLAUDE_CODE_ALIGNMENT.md`
