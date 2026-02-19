# MEMORY.md

## Stable Decisions

- Region: Amazon US
- Language: English
- Format: Hybrid (long + Shorts)
- Price floor: $100+
- Use AI avatar + disclosure

## Compliance

- Always include: "As an Amazon Associate I earn from qualifying purchases."
- Include AI disclosure in description and (ideally) in-video.

## Trending Workflow

- Daily trend scan uses YouTube Data API.
- Rank by view velocity (views per hour) in last 48h window.
- Use trends only for structure, not copying.
- For TikTok/Reels, use official trend sources and in-app trend discovery.

## Production Standards

- Use fixed templates for avatar, font, and style.
- Generate voiceover in 60–90 second segments.
- Always add captions before export.
- Run QA checklist before publishing.
- Keep an asset manifest with source URL + usage note per visual.
- Use only APPROVED assets for final edit.

## Refinement Loop

- Use SEO + Editor + Reviewer passes.
- Limit to two iterations.

## Ops Loop

- Local closed-loop tooling in /Users/ray/Documents/Rayviews/ops with driver script /Users/ray/Documents/Rayviews/tools/ops_loop.py.
- Steps: trend_scan → research → script → seo → edit → review → qa → export → upload.

## Asset Strategy

- Added dedicated `asset_hunter` specialist for image/video sourcing.
- Source priority: official media → Amazon listing context → licensed stock → AI-generated support visuals.
- No copyrighted clips/music without explicit license.
