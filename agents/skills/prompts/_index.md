---
description: MOC for prompt engineering — templates, structure, per-variant strategies.
tags: [moc, prompts, engineering]
created: 2026-02-19
updated: 2026-02-19
---

# Prompt Engineering Skills

How to write prompts that produce visually distinct product photography.

## Variant Prompts (one per shot type)

Each variant MUST produce a visually distinct result. If outputs look identical, the tool or prompt is wrong.

- [[hero-shot]] — Premium studio isolation. Dark surface, dramatic lighting, product as star.
- [[lifestyle-shot]] — Product in real-world context. Home, office, kitchen. Natural light, depth of field.
- [[detail-shot]] — Macro close-up. White/neutral BG, sharp focus on texture and build quality.
- [[mood-shot]] — Editorial/cinematic. Dramatic light, atmosphere, emotion. Storytelling.
- [[usage-variation]] — Alternative lifestyle context. Different room/angle than primary lifestyle.

## Prompt Structure

Every effective prompt follows this modular framework (see [[prompt-structure]]):

```
[SHOT TYPE] of [PRODUCT + MATERIALS] on [SURFACE].
[ENVIRONMENT]. [LIGHTING]. [CAMERA]. [MOOD].
```

## Tool-Prompt Matrix

Which prompts work with which tools — see [[tool-prompt-matrix]].

## Key Rules

1. **Specificity wins**: "warm oak hardwood floor" beats "nice floor"
2. **4-6 high-signal details**: Don't overload. Surface, lighting, camera, mood.
3. **Photographic language**: "three-point lighting", "85mm lens", "shallow DOF"
4. **Mention product briefly**: Type + 1-2 features, then focus on SCENE
5. **Never use vague words**: "nice", "good", "beautiful" get ignored by AI

## Anti-Patterns (from [[../learnings/2026-02-19-identical-images]])

- Using [[../dzine/generative-expand]] with scene prompts → prompts are ignored
- Generic backdrop descriptions ("clean studio") → identical outputs
- Missing lighting specification → AI defaults to flat even lighting
- No camera angle → random/default perspective

Full prompt templates: `agents/dzine_prompt_library.md`
