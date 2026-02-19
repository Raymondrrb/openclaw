# YouTube Daily Posting SOP (Ray)

Scope: Amazon US review videos, English deliverables, affiliate + AI disclosure required.

## Recommended stack

- Script/research/SEO/QA: OpenClaw agents.
- Voice: ElevenLabs.
- Editing: Fliki or InVideo (web) for speed.
- Upload/scheduling: YouTube Studio (manual final click).

## Daily flow (1 long + 2 shorts)

1. Generate episode package

- Run:
  `/usr/bin/python3 /Users/ray/Documents/Rayviews/tools/market_auto_dispatch.py --date TODAY --notify-agents --wait-seconds 420 --max-long-videos-per-day 1`
- Outputs expected in `content/auto_<slug>_<date>/`:
  - `research.md`
  - `script_long.md`
  - `seo_package.md`
  - `review_final.md`
  - `edit_strategy.md`
  - `quality_gate.md`
  - `asset_manifest.md`
  - `video_safe_manifest.md`

2. Voice production (ElevenLabs)

- Use `script_long.md` and generate in chunks.
- Save MP3 chunks to:
  `content/<slug>/voiceover/`

3. Edit production (Fliki/InVideo)

- Import voice chunks + use only `assets/video_safe/*_16x9.jpg`.
- Follow `edit_strategy.md` for pacing and retention map.
- Keep background music under narration (ducking).

4. Export

- Long video: 1080p 16:9.
- Shorts: 1080x1920 (crop from high-performing moments).

5. Upload in YouTube Studio

- Title/description/tags from `seo_package.md`.
- Paste affiliate links.
- Ensure disclosures are present:
  - Affiliate disclosure
  - AI disclosure
- Add chapters, thumbnail, end screen, cards.
- Schedule publish time.

## Quality benchmark loop (daily)

1. Benchmark refresh:

- `benchmark_analyst` updates reference playbooks from watchlist links.

2. Pre-publish gate:

- `quality_gate` must return PASS (`>=85`) before final publish.

3. If FAIL:

- apply fixes from `quality_gate.md` or `quality_fixes.md`, then re-run gate.

## Manual steps that should stay manual

- Final quality watch-through.
- Final legal/compliance check.
- Final publish click.

## When to use local editor (DaVinci/CapCut) vs web (Fliki/InVideo)

- Use Fliki/InVideo for speed and daily volume.
- Use DaVinci/CapCut when you need advanced motion design, cleaner audio chain, or custom transitions for higher-quality flagship videos.

## Minimum quality gate before publish

- No stretched/portrait screenshots in timeline.
- Voice clear, no clipping, no long silence gaps.
- Value delivered before CTA.
- Metrics phrasing includes "at time of recording".
- Affiliate + AI disclosure present in description.
