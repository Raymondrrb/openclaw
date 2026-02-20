---
description: Telegram approval contract for low-noise RayViewsLab runs.
tags: [pipeline, telegram, approvals, low-noise]
created: 2026-02-20
updated: 2026-02-20
---

# Telegram Approval Matrix

Use Telegram as the mandatory human gate without spamming heartbeat updates.

## Stage Ownership

- `niche` -> `market_scout`
- `products` -> `researcher`
- `assets` -> `dzine_producer`
- `gate1` -> `reviewer`
- `gate2` -> `quality_gate`
- `render` -> `publisher`

## Approval Policy

When `--telegram-approvals` is enabled in `tools/pipeline.py run-e2e`:

1. `niche` approval before product discovery
2. `products` approval after shortlist generation
3. `gate1` approval for products + script
4. `assets` image approval (sampled variants)
5. `gate2` approval for assets + voice + compliance

If any stage is rejected, run stops immediately.

## Low-Noise Rule

- No periodic heartbeat notifications.
- Telegram messages are only:
  - blocking approvals
  - explicit failures

This minimizes API spend and notification fatigue.

## Recommended Command

```bash
python3 tools/pipeline.py run-e2e \
  --category "portable_monitors" \
  --telegram-approvals \
  --telegram-stages "niche,products,assets,gate1,gate2" \
  --telegram-assets-per-product 1 \
  --telegram-timeout-sec 1800
```
