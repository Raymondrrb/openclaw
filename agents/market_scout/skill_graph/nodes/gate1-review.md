---
id: gate1-review
title: Gate 1 Review Contract
description: Defines mandatory package content and block conditions for the first human approval gate.
tags: [gate1, approval, contract, quality]
links: ["[[prompt-injection-defense]]", "[[affiliate-compliance]]", "[[observability-receipts]]"]
---

# Gate 1 Review Contract

Gate 1 package must include category, five products, ASIN, price, rating, review count, and affiliate link.

## Blocking Rule

- Block only when status is FAIL (security/compliance contract breach).
- WARN does not block; warnings must be surfaced in the package summary.

## Audit Rule

Write reason codes and decision metadata to run receipts and events for traceability.
