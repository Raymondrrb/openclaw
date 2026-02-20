# RayViewsLab Agent Operating Standard

## Workspace Boundary (Critical)

- This folder is the canonical workspace.
- Canonical workspace for RayViewsLab: `/Users/ray/Documents/openclaw`
- Canonical GitHub remote: `rayviewslab` (`https://github.com/Raymondrrb/rayviewslab.git`)
- If this folder is opened by mistake, stop and switch to `/Users/ray/Documents/openclaw`.

## Workflow Orchestration

### 1) Plan Mode Default

- Enter plan mode for any non-trivial task (3+ steps or architectural decisions).
- If something goes sideways, stop and re-plan immediately.
- Use plan mode for verification work, not only implementation.
- Write detailed specs up front to reduce ambiguity.

### 2) Subagent Strategy

- Use subagents to keep main context focused.
- Offload research/exploration and parallel analysis to subagents.
- For complex problems, use multiple focused subagents (one task per subagent).

### 3) Self-Improvement Loop

- After any user correction, append a lesson to `tasks/lessons.md`.
- Write a prevention rule that avoids repeating the same mistake.
- Review relevant lessons at session start.

### 4) Verification Before Done

- Never mark done without proof.
- Run tests, inspect logs, and show behavior deltas when relevant.
- Final quality bar: “would a staff engineer approve this change?”

### 5) Demand Elegance (Balanced)

- For non-trivial changes, actively evaluate if there is a cleaner design.
- If fix is hacky, re-implement elegantly with minimal complexity.
- Do not over-engineer obvious/simple fixes.

### 6) Autonomous Bug Fixing

- On bug report, investigate and fix directly.
- Use failing tests/log evidence; avoid unnecessary user context switching.
- Fix failing CI tests proactively.

## Task Management

- Plan first in `tasks/todo.md` with checkable items.
- Track progress by checking items during execution.
- Add a short review section at end of task.
- Record lessons in `tasks/lessons.md` after corrections.

## Core Principles

- Simplicity first: minimal, targeted changes.
- No laziness: root-cause fixes, no temporary patches.
- Minimal impact: touch only necessary scope and protect stability.
