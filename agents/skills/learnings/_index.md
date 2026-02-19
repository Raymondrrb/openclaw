---
description: Auto-recorded lessons from pipeline runs. Newest first. Check this BEFORE every pipeline run to avoid repeating mistakes.
tags: [moc, learnings, auto-improvement, memory]
created: 2026-02-19
updated: 2026-02-19
---

# Learnings (Auto-Improvement Log)

Every pipeline run records its outcome here. Before starting any generation, the agent MUST scan this index to avoid repeating documented failures.

## Protocol

1. **Before run**: Read this index. Check for relevant failures.
2. **After run**: Create new learning node with date prefix.
3. **If prompt failed**: Mark old prompt as `status: deprecated`, create improved version.
4. **If tool was wrong**: Update tool node with failure context.
5. **Format**: `YYYY-MM-DD-short-description.md`

## Recent Learnings (newest first)

- [[2026-02-19-identical-images]] — **CRITICAL**: Generative Expand ignores scene prompts. All 18 images came out identical. Switch to Product Background.
- [[2026-02-19-phone-removal]] — BG Remove treats phones as foreground. Must crop from reference before upload.
- [[2026-02-19-duplicate-dock]] — Tapo RV30 Expand created phantom second dock. Fixed with clean alternate Amazon image.
- [[2026-02-19-playwright-crash]] — Playwright "Sync API inside asyncio loop" when creating new instance per call. Fixed with shared session pattern.

## Patterns

### Recurring Theme: Tool Mismatch

Multiple failures trace to using the wrong Dzine tool:

- Generative Expand for scene variation (should use Product Background)
- Img2Img for faithful reproduction (should use BG Remove + scene tool)

### Recurring Theme: Reference Image Quality

Bad reference images cascade into bad outputs:

- Phones in reference → phones in output ([[2026-02-19-phone-removal]])
- Complex backgrounds → artifacts in expand ([[2026-02-19-duplicate-dock]])

## Statistics

| Date       | Video    | Generated | Failed | Avg Score       | Key Issue             |
| ---------- | -------- | --------- | ------ | --------------- | --------------------- |
| 2026-02-19 | vtest-qa | 18/18     | 0      | 9.8/10 fidelity | Identical backgrounds |
