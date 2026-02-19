---
description: Maps which prompts work with which Dzine tools. Critical for avoiding the Generative Expand mistake.
tags: [prompt, tools, matrix, decision]
created: 2026-02-19
updated: 2026-02-19
status: proven
---

# Tool-Prompt Matrix

Not all tools respond to prompts equally. This matrix prevents wasting credits on tools that ignore your prompt.

## Matrix

| Tool                     | Prompt Influence | Describe Product?  | Describe Scene?       | Max Chars |
| ------------------------ | ---------------- | ------------------ | --------------------- | --------- |
| **Product Background**   | HIGH             | No (auto-detected) | YES — scene only      | TBD       |
| **Img2Img**              | HIGH             | Yes (full scene)   | Yes (full scene)      | 1800      |
| **Txt2Img**              | HIGH             | Yes (full scene)   | Yes (full scene)      | 1800      |
| **Generative Expand**    | MINIMAL          | Ignored            | Mostly ignored        | 1800      |
| **Local Edit**           | MEDIUM           | No (masked area)   | Describe fill content | 1800      |
| **Insert Object**        | LOW              | Brief description  | No                    | 150       |
| **CC (Consistent Char)** | HIGH             | Yes (character)    | Yes (full scene)      | 1800      |

## Key Insight

For **Product Background**: describe ONLY the environment/scene. The product is preserved automatically.
For **Img2Img**: describe EVERYTHING — product + scene. Include "product unmodified" as guardrail.
For **Generative Expand**: prompts are effectively ignored. Don't waste effort writing detailed prompts.

## Variant-to-Tool Mapping

| Variant   | Recommended Tool   | Prompt Type                         |
| --------- | ------------------ | ----------------------------------- |
| hero      | Product Background | Scene-only ([[hero-shot]])          |
| usage1    | Product Background | Scene-only ([[lifestyle-shot]])     |
| usage2    | Product Background | Scene-only ([[usage-variation]])    |
| detail    | Product Background | Scene-only ([[detail-shot]])        |
| mood      | Product Background | Scene-only ([[mood-shot]])          |
| thumbnail | Txt2Img + CC       | Full scene (prompt library T01-T03) |

## Previous Mistake

Using Generative Expand for all variants with scene prompts → all 18 images came out with identical plain backgrounds. See [[../learnings/2026-02-19-identical-images]].
