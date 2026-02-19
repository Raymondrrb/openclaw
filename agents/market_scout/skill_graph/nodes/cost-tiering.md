---
id: cost-tiering
title: Cost and Ops Tiering
description: Uses objective run signals to set normal, low_compute, critical, or paused modes.
tags: [ops, budget, tier, reliability]
links: ["[[distributed-execution]]", "[[gate1-review]]", "[[observability-receipts]]"]
---

# Cost and Ops Tiering

Tier should be computed before expensive steps like voice, assets, and render.

## Priority Order

1. paused: manual pause file or environment pause flag.
2. critical: credit exhaustion, repeated failures, disk pressure, worker offline.
3. low_compute: budget nearing limit or configured cost-saving window.
4. normal: healthy state.

Always emit reasons array in the tier report.
