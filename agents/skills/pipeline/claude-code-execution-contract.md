---
description: Contract prompt for Claude Code to avoid unstable OpenClaw execution patterns.
tags: [pipeline, claude-code, operations, reliability]
created: 2026-02-19
updated: 2026-02-19
---

# Claude Code Execution Contract

Use this prompt when starting a new implementation session.

## Prompt

```text
You are working in /Users/ray/Documents/Rayviews.
Before changes, read:
- /Users/ray/Documents/Rayviews/README.md (OpenClaw stability guardrails)
- /Users/ray/Documents/Rayviews/tasks/lessons.md

Hard rules:
1) Never implement 1s polling loops that call `openclaw browser` repeatedly.
2) Use one `openclaw browser wait --fn` with explicit timeout.
3) Do not run parallel ChatGPT UI automation loops.
4) Every OpenClaw browser command must have timeout and failure handling.
5) If process pressure rises, run `tools/openclaw_recover.sh` and continue only after recovery.
6) Show proof: tests/logs/command outputs before marking done.

Now propose a short plan and implement with minimal process churn.
```

## Why This Exists

This prevents regressions where automation creates OpenClaw process storms and degrades the whole workstation.

## Operational Pairing

Use together with [[openclaw-stability-guardrails]] for preflight + recovery.
