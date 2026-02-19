# Dzine Experiments — 2026-02-08

## Experiment Set (playbook)

1. Lip sync smoothness settings
2. Product reference fidelity
3. Thumbnail CTR framing patterns

Cycle type: artifact-driven (no fresh full render batch due active export blocker).

---

## EXP-01 — Lip Sync Smoothness via export-safe sequencing

### Hypothesis

An early export checkpoint after S01 preserves smoothness tuning time and prevents wasted generation when export is unstable.

### Method

- Reviewed latest `dzine_generation_report.md`, `dzine_asset_manifest.md`, and `dzine_blockers.md` from 2026-02-07 episode.

### Result (winner)

- Sequence winner: **Generate S01 -> verify successful export -> continue S02+**.
- Rationale: S01 was generated but non-exportable, proving batch continuation is risky before confirming export path.

### Confidence

**High**.

### Next run metrics

- blocked minutes avoided
- retry count/session
- exported-scene success rate

---

## EXP-02 — Product reference fidelity enforcement

### Hypothesis

Binary rejection criteria (shape, controls, branding, ambiguity) produce better consistency than subjective approval.

### Method

- Audited existing fidelity gate usage in prompt pack/manual and mapped to manifest execution rules.

### Result (winner)

- Keep strict reject/regenerate gate and log failure reason per scene.

### Confidence

**Medium** (process validated; no fresh quantified 10-variant run this cycle).

### Next run

- Execute 10 product-focused variants and count failure modes by prompt style.

---

## EXP-03 — Thumbnail CTR framing shortlist

### Hypothesis

Direct rivalry framing (TH-A/TH-C style) should outperform abstract framing for comparison episodes.

### Method

- Audited latest thumbnail concepts and classified by tension/readability style.

### Result

- Primary next-live shortlist: **TH-A + TH-C**.
- Secondary: TH-B + TH-D.

### Confidence

**Low-to-Medium** (awaiting live CTR readout).

### Next run

- Enforce naming tags and collect 24h + 72h CTR deltas.

---

## Operational Experiment Added

## EXP-04 — Episode handoff integrity check

### Hypothesis

Requiring all four Dzine output files before status promotion reduces false “in-progress/complete” claims.

### Method

- Audited newest episode folder `auto_opportunity_2026-02-08` for required Dzine artifacts.

### Result

- Folder contains only `dzine_producer_task.md`; therefore Dzine status should be `NOT_STARTED`.

### Confidence

**High**.

### Next run

- Add automated pre-publish check for file presence and fail fast when missing.
