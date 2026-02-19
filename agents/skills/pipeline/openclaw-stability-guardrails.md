---
description: Operational guardrails to prevent OpenClaw process storms and Mac slowdowns.
tags: [pipeline, openclaw, reliability, runbook]
created: 2026-02-19
updated: 2026-02-19
---

# OpenClaw Stability Guardrails

Use this before any ChatGPT UI automation run.

## Symptoms

- Mac CPU high with many `openclaw` / `openclaw-channels` processes.
- System lag, browser delays, and unstable agent runs.

## Root Cause Pattern

High-frequency polling implemented as repeated CLI subprocess calls (`openclaw browser ...`) can cause process storms and orphan processes.

## Prevention Contract

1. Prefer a single `wait --fn` with timeout over polling loops.
2. Never run parallel loops calling `openclaw browser evaluate/tabs/status` every second.
3. Serialize browser CLI calls with a local file lock.
4. Enforce hard timeout on every OpenClaw browser command.
5. Run a preflight health check before long runs.

## Recovery Runbook

From `/Users/ray/Documents/Rayviews`:

```bash
# Inspect only
tools/openclaw_recover.sh

# Recover orphans and restart managed browser service
tools/openclaw_recover.sh --apply --restart-browser
```

## Where This Is Implemented

- `tools/chatgpt_ui.py`
  : lock + throttle + per-command timeout + single-wait response flow.
- `tools/pipeline.py`
  : less aggressive polling fallback (`poll_sec=2.5`).
- `tools/openclaw_recover.sh`
  : orphan detection and cleanup utility.

## Related Nodes

- [[claude-code-execution-contract]]
- [[asset-quality-gate]]
