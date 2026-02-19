---
description: "Reference image had visual clutter and ambiguous shapes near the dock area. Generation model interpreted the pattern as an extra dock. → 1. Switched to a cleaner alternate Amazon reference.
2. Cropped reference tighter around product + real dock.
3. Re-generated with explicit prompt constraint: one dock only."
tags: [learning, learning, learning-event, fail, unknown]
created: 2026-02-19
severity: fail
video_id: 
affected_tools: []
fix: 1. Switched to a cleaner alternate Amazon reference.
2. Cropped reference tighter around product + real dock.
3. Re-generated with explicit prompt constraint: one dock only.
---

# [FAIL] unknown: Generated image added a second charging dock that did not ex

## Symptom

Generated image added a second charging dock that did not exist in the intended scene.

## Root Cause

Reference image had visual clutter and ambiguous shapes near the dock area. Generation model interpreted the pattern as an extra dock.

## Fix Applied

1. Switched to a cleaner alternate Amazon reference.
2. Cropped reference tighter around product + real dock.
3. Re-generated with explicit prompt constraint: one dock only.

## Verification

Before generation, reject references with ambiguous duplicate-like structures in the foreground/background.
