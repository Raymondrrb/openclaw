---
description: Objective gate for generated visual assets before Gate 2 approval.
tags: [pipeline, quality-gate, validation]
created: 2026-02-19
updated: 2026-02-19
status: enforced
---

# Asset Quality Gate

This gate defines pass/fail for generated image assets before render/upload.

## Required Checks (FAIL if any fails)

1. File exists for every required variant (minimum 2 per product, target 3).
2. Resolution is at least 1920x1080.
3. File size is greater than 150 KB.
4. Product identity is preserved (manual or classifier score threshold).
5. At least one thumbnail candidate exists.

## Warning Checks (WARN only)

- Scene variety score below target (images too similar)
- Minor lighting inconsistency
- Low typography-safe empty area for price overlay

## Gate Policy

- `FAIL` blocks progression to render.
- `WARN` is allowed but must be listed in Gate 2 package.

## Output Contract

Write a machine-readable report:

- `security/input_guard_report.json` (if input guard participated)
- `ops/ops_tier_report.json` (cost/tier context)
- `assets_manifest.json` (produced files)
- `asset_quality_report.json` (this gate verdict with reason codes)
