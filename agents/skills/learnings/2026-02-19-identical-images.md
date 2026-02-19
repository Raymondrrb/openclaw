---
description: "CRITICAL: Generative Expand ignores scene prompts. All 18 product images had identical plain backgrounds despite 5 different backdrop prompts."
tags: [failure, generative-expand, prompts-ignored, critical]
created: 2026-02-19
severity: critical
video_id: vtest-qa
affected_tools: [generative-expand]
fix: switch-to-product-background
---

# Identical Images from Generative Expand

## What Happened

Generated 18 product images for vtest-qa using BG Remove + Generative Expand with 5 different backdrop prompts:

- hero: "Premium dark studio surface with subtle reflections..."
- usage1: "Modern living room hardwood floor..."
- usage2: "Bedroom wooden floor..."
- detail: "Clean white studio surface..."
- mood: "Dramatic dark surface with volumetric light rays..."

All 18 images came out with nearly identical plain neutral backgrounds. The product was preserved perfectly (9.8/10 fidelity) but there was ZERO scene variation.

## Root Cause

Generative Expand is a **canvas extension tool**, NOT a scene generator. It fills the expanded area by continuing the edge pixels of the existing image. The prompt field exists but has minimal influence on the output.

When the input is a product with transparent background (from BG Remove), Expand just generates a uniform gradient matching the product's edge colors.

## Evidence

- 5 variants of Roborock Q7: all show product floating on plain gray/white gradient
- MD5 hashes differ (not byte-identical) but visually indistinguishable
- Living room, bedroom, studio prompts all produced the same output

## Fix

Replace Generative Expand with **Product Background** tool in the pipeline:

1. Product Background is designed specifically for scene generation
2. It accepts and respects scene prompts
3. It handles BG removal internally
4. Position: Image Editor > Product Background (92, 877), requires scrolling

See [[../dzine/product-background]] for automation details.
See [[../prompts/_index]] for variant-specific prompts.

## Prevention

- NEVER use Generative Expand for scene variation
- ALWAYS check [[../prompts/tool-prompt-matrix]] before choosing a tool
- If outputs look identical across variants, the tool is ignoring prompts
