---
description: Root entry point for the RayviewsLab skill graph. Scan this first.
tags: [index, navigation, entry-point]
created: 2026-02-19
updated: 2026-02-19
---

# RayviewsLab Skill Graph

Interconnected knowledge base for autonomous video production agents.
Each node is one complete thought. Follow [[wikilinks]] to go deeper.

## How to Navigate

1. Read this index — understand the landscape
2. Follow the MOC links below for your domain
3. Each node has YAML `description:` — scan it before reading the full file
4. Wikilinks in prose carry meaning — follow relevant paths, skip the rest
5. After every pipeline run, check [[learnings/_index]] for recent lessons

## Domain MOCs

- [[dzine/_index]] — Dzine platform: tools, models, workflows, automation
- [[prompts/_index]] — Prompt engineering: templates, structure, per-variant strategies
- [[pipeline/_index]] — Pipeline architecture: asset generation, validation, orchestration
- [[learnings/_index]] — Auto-recorded lessons from pipeline runs (newest first)

## Cross-Domain Insights

- [[dzine/product-background]] is the correct tool for scene variation, NOT [[dzine/generative-expand]] which only extends canvas uniformly
- Prompt quality depends on tool choice — [[prompts/tool-prompt-matrix]] maps which prompts work with which tools
- The [[pipeline/product-faithful]] workflow must select the best of 4 results, not blindly take the first — see [[learnings/2026-02-19-identical-images]]
- Runtime stability is part of quality: enforce [[pipeline/openclaw-stability-guardrails]] before long browser-driven runs

## Auto-Improvement Protocol

After every pipeline run, the agent MUST:

1. Evaluate visual results (fidelity score, variety score)
2. Record outcome in [[learnings/_index]] as a new node
3. If a prompt failed → update the prompt node with `status: deprecated` and create improved version
4. If a tool was wrong → update the tool node with failure context
5. Never repeat a documented failure — always check [[learnings/_index]] first

## Reference Appendices (flat files, not skill nodes)

These large reference files contain detailed coordinates and mappings. Nodes link to them for specifics:

- `agents/dzine_playbook.md` (2691 lines) — Full UI coordinates and automation code
- `agents/dzine_ui_map.md` (1516 lines) — Complete sidebar/panel position map
- `agents/dzine_prompt_library.md` (381 lines) — All prompt templates with IDs
- `agents/dzine_failures.md` (448 lines) — Failure playbook with fix code
