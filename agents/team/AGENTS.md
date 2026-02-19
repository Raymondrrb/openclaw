# Agent Ops (YouTube Reviews) - Lean Core

Purpose: run one reliable daily long-video pipeline with fewer agents and stronger role definitions.

Source of truth for active roster: `agents/team/ACTIVE_AGENTS.json`.

## Active Core Team (7)

1. `market_scout` - market pulse and opportunity selection
2. `researcher` - research + affiliate links
3. `scriptwriter` - script + SEO package
4. `reviewer` - review + edit strategy + quality gate
5. `dzine_producer` - shot plan + asset manifest + Dzine package
6. `davinci_editor` - DaVinci edit plan and export QC
7. `publisher` - publish package + upload payload (stop before final publish)

## Standby/Optional Agents

- `affiliate_linker`, `asset_hunter`, `seo`, `edit_strategist`, `quality_gate`, `youtube_uploader`
- `benchmark_analyst`, `dzine_researcher`, `davinci_researcher`, `researcher2`

These remain for compatibility or deep-study tasks, but are not required in the daily loop.

## Golden Rules

- Use only verifiable facts from Amazon listings and trusted sources.
- No invented ratings, reviews, links, or claims.
- Always include affiliate + AI disclosure.
- Keep no-repeat policy for products in last 15 days.
- One long video per day by default.

## Memory Rules

1. Read `agents/memory/WORKING.md`
2. Read `agents/memory/MEMORY.md`
3. Read today's and yesterday's daily notes
4. Persist key decisions in files, not chat

## Refinement Loop

1. Draft pass
2. Reviewer pass
3. One correction pass if critical issues remain
4. Publish when gate is PASS and links are valid
