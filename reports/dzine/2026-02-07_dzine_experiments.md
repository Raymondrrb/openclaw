# Dzine Experiments — 2026-02-07

## Experiment Set

Required by playbook:

1. Lip sync smoothness settings
2. Product reference fidelity
3. Thumbnail CTR framing patterns

Note: This cycle used one real in-app run artifact from today plus evidence-backed protocol updates. Full multi-variant generation is partially blocked by export/UI state in current project.

---

## EXP-01 — Lip Sync Smoothness (segment strategy)

### Hypothesis

Short-to-mid chunks (45–90s) remain more controllable than long single-pass clips for daily production, even if Dzine claims up to 5-minute dialogue support.

### Method (today)

- Reviewed current production policy (45–90s chunking).
- Collected official claim (up to 5-minute dialogue support).
- Cross-checked real run status from today’s project (`S01 generated; export blocked`).

### Result

- **Winner for now:** 45–90s chunking (operational default).
- Rationale: safer iteration, easier retakes, less downstream pain when export path is unstable.

### Confidence

**Medium** (strong operational logic + official long-form claim, but no completed internal A/B timing dataset yet).

### Next run to raise confidence

- Execute A/B on same script:
  - Arm A: 3x ~70s chunks
  - Arm B: 1x ~210s chunk
- Measure: retake count, perceived lip drift, transition artifacts, generation minutes, export success rate.

---

## EXP-02 — Product Reference Fidelity

### Hypothesis

Product scenes stay trustworthy only when generated outputs are evaluated against a strict reference checklist (shape/button/logo/camera-port geometry), not visual appeal alone.

### Method (today)

- Validated Dzine official product-photography workflow focus (background manipulation + generated presentation).
- Compared against Amazon-review requirements in our flow (truthful product depiction).

### Result

- **Winner:** strict fidelity gate before accepting scene.
- Enforced evaluation rule:
  1. Silhouette match
  2. Button/port/control placement match
  3. Logo/branding placement consistency
  4. Reject outputs where style enhancement distorts product identity

### Confidence

**Medium** (evidence-backed capability + domain requirement; internal quantified pass-rate test pending).

### Next run to raise confidence

- 10-scene benchmark with binary pass/fail by checklist; track failure modes by prompt style.

---

## EXP-03 — Thumbnail CTR Framing Patterns

### Hypothesis

First-frame product clarity and text-safe composition should outperform stylistic complexity for Amazon comparison content.

### Method (today)

- Used current quality criteria from manual and existing episode constraints.
- Focused on practical patterns for 3–5 thumbnail variants.

### Result

- **Current winning pattern set:**
  - Pattern A: split-product faceoff, high contrast, clear central subject
  - Pattern B: presenter + hero product close-up with empty side for text
  - Pattern C: verdict hint visual (badge/checkmark) without clutter
- Hard reject rules:
  - Busy backgrounds reducing 2-second readability
  - Product too small for mobile feed

### Confidence

**Low-to-Medium** (best-practice reasoning; no fresh CTR dataset captured in this cycle).

### Next run to raise confidence

- Ship 3 variants with tagged naming and pull 24–72h CTR deltas from publishing platform.

---

## Blockers observed in this cycle

1. **Export button disabled** despite generation complete in current run.
2. Requires explicit editor/canvas activation sequence before export retry.

See: `content/auto_airpods_pro_3_vs_bose_qc_ultra_2nd_gen_which_250_2026-02-07/dzine_blockers.md`

---

## Operational decisions adopted today

1. Keep **45–90s** as production default for lip sync chunks.
2. Route **2–4 speaker scenes** to Multi-Character Lip Sync flow.
3. Treat product fidelity as a hard gate (not subjective quality preference).
4. Run preflight plan check before generation-heavy sessions.
