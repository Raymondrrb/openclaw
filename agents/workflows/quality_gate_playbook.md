# Workflow: Quality Gate

Goal: prevent low-quality episodes from moving to final production.

## Inputs

- `content/<slug>/script_long.md`
- `content/<slug>/seo_package.md`
- `content/<slug>/review_final.md`
- `content/<slug>/edit_strategy.md`
- `content/<slug>/asset_manifest.md` (or `video_safe_manifest.md`)
- Benchmark file in `reports/benchmarks/`

## Required output

- `content/<slug>/quality_gate.md`

## Decision rule

- PASS if score >= 85 and no hard-fail condition.
- FAIL otherwise.

## Hard-fail conditions

- Missing affiliate or AI disclosure.
- Missing `affiliate_links.md` or unresolved affiliate placeholders.
- No trustworthy source trail for core claims.
- Visual pack not suitable for final timeline (no video-safe assets).

## Report format

1. Scorecard by category
2. PASS/FAIL
3. Top 5 fixes
4. Fast re-check checklist
