---
description: Dzine failure map with links to root-cause learnings and mitigations.
tags: [moc, dzine, failures, recovery]
created: 2026-02-19
updated: 2026-02-19
---

# Dzine Failures

Use this page as the first stop when an automation or generation step fails.

## Known Failures

- [[../../learnings/2026-02-19-identical-images]] — wrong tool (`Generative Expand`) used for scene variation.
- [[../../learnings/2026-02-19-phone-removal]] — reference image contamination (phone included as foreground).
- [[../../learnings/2026-02-19-duplicate-dock]] — phantom duplicate dock generated from noisy reference.
- [[../../learnings/2026-02-19-playwright-crash]] — session lifecycle bug in Playwright.

## Triage Order

1. Validate reference image quality
2. Validate selected Dzine tool vs goal
3. Validate popup/dialog handling
4. Validate generation prompt constraints
