---
id: observability-receipts
title: Observability and Receipts
description: Standardizes per-step logs, hashes, reason codes, and receipts for auditable deterministic runs.
tags: [receipts, observability, idempotency, audit]
links: ["[[gate1-review]]", "[[distributed-execution]]"]
---

# Observability and Receipts

Each step should produce a receipt with status, hashes, timings, and artifact pointers.

## Required Fields

- status and exit code
- inputs hash and outputs hash
- tool versions and host fingerprint
- reason codes and retry counters

Also emit lightweight ops events for dashboard visibility.
