---
description: Script quality standards and feedback loop. Agents MUST check this before generating or refining scripts.
tags: [learning, script, quality, critical, auto-improvement]
created: 2026-02-19
updated: 2026-02-19
severity: high
status: active
---

# 2026-02-19 — Script Quality Rules

## Core Principles

1. **Authenticity above all** — scripts must sound like a real human reviewer, not AI-generated content
2. **Honest downsides** — every product MUST have real downsides. Viewers trust honest reviews
3. **No hype words** — ban: "game-changer", "revolutionary", "incredible", "amazing", "best ever"
4. **No AI cliches** — ban: "let's dive in", "without further ado", "in this video"
5. **Disclosure** — affiliate disclosure must be present and natural
6. **Refine until satisfied** — no limit on refinement passes. Quality > speed

## Feedback Loop Protocol

After EVERY script generation:

1. **Check word count** — must be within target range for video length
2. **Check sections** — all required markers present (HOOK, PRODUCT_5..1, RETENTION_RESET, CONCLUSION)
3. **Check tone** — read aloud mentally. Does it sound human? Natural? Conversational?
4. **Check downsides** — each product must have honest negatives
5. **Check disclosure** — affiliate link disclosure present
6. **Save feedback** — record what worked and what didn't as a learning node

## Known Script Failures

| Pattern                         | Root Cause                                   | Fix                         |
| ------------------------------- | -------------------------------------------- | --------------------------- |
| Identical backgrounds in images | Used Generative Expand                       | Use Product Background      |
| Browser LLM informal markers    | ChatGPT/Claude use #5 instead of [PRODUCT_5] | normalize_section_markers() |
| Missing metadata                | Browser Claude uses different format         | Updated extract_metadata()  |
| 0 words reported                | Parser didn't recognize informal sections    | Normalization layer added   |

## Text Feedback Storage

All text generation feedback MUST be saved to:

- This node (for patterns)
- New learning nodes (for specific failures)
- The skill graph prompt nodes (for prompt improvements)

When a prompt produces bad output:

1. Mark old prompt version as `status: deprecated`
2. Create improved version with the fix
3. Record what went wrong as a learning

## Related Nodes

- [[../prompts/hero-shot]]
- [[../prompts/lifestyle-shot]]
- [[../prompts/detail-shot]]
- [[../prompts/mood-shot]]
- [[../prompts/usage-variation]]
- [[2026-02-19-image-qa-rules]]
