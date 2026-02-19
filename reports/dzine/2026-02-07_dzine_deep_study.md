# Dzine Deep Study — 2026-02-07

## Scope

- Workflow reference: `agents/workflows/dzine_deep_study_playbook.md`
- Baseline manual reviewed: `agents/knowledge/dzine_operator_manual.md` (pre-update)
- Evidence sources:
  1. Official Dzine pages fetched on 2026-02-07:
     - https://www.dzine.ai/
     - https://www.dzine.ai/pricing/
     - https://www.dzine.ai/tools/lip-sync-ai-video/
     - https://www.dzine.ai/tools/multiple-lip-sync/
     - https://www.dzine.ai/tools/ai-product-photography/
  2. In-app run artifact from today:
     - `content/auto_airpods_pro_3_vs_bose_qc_ultra_2nd_gen_which_250_2026-02-07/dzine_generation_report.md`
     - `content/auto_airpods_pro_3_vs_bose_qc_ultra_2nd_gen_which_250_2026-02-07/dzine_blockers.md`

---

## Findings (with confidence)

### F1) Multi-character lip sync capacity is now explicitly positioned as up to 4 faces

- Evidence:
  - Dzine lip sync page states up to 4 characters.
  - Dzine multiple lip sync page reinforces multi-face capability and 4-face positioning.
- Operational impact:
  - Current internal manual does not yet state a practical runbook for 1-face vs 2-4 face use.
  - Team should route group-dialogue scenes to Multi-Character Lip Sync and avoid forcing single-face flow.
- Confidence: **Medium** (official marketing/product pages, but not yet validated by our own 4-face production test).

### F2) Dzine positions lip-sync length support up to 5-minute dialogue videos

- Evidence:
  - Lip sync tool page claims support for continuous 5-minute dialogue videos.
- Operational impact:
  - Existing daily flow says 45–90s chunks. This remains safer for stability/control.
  - We can add a conditional long-form mode (2–5 min) only when continuity is more important than retake granularity.
- Confidence: **Medium** (official page claim; no internal long-form stress test completed yet).

### F3) Export reliability still depends on active canvas/editor state in practice

- Evidence:
  - In-app blocker log from today: generated result visible, export disabled until result is opened in Image Editor/canvas with active layer.
- Operational impact:
  - Existing manual has this recovery at high level; should be made explicit as a deterministic checklist before declaring blocker.
- Confidence: **High** (direct in-app observation today).

### F4) Plan-level capability differences materially affect quality/cost decisions

- Evidence:
  - Pricing page lists video credits, concurrent video jobs, multi-character lip sync availability, and upscaling ceilings (e.g., 1080p on lower paid tier, up to 8K on top tier).
- Operational impact:
  - Manual should require plan check before episode kickoff to avoid avoidable failures (queue delay, upscale mismatch, credit exhaustion).
- Confidence: **Medium** (official pricing page; plan labels/details can change quickly).

### F5) Product-image workflows are officially supported, but fidelity guardrails remain necessary

- Evidence:
  - Product photography tool page emphasizes background replacement and fast visual generation.
- Operational impact:
  - For Amazon review use case, we should continue strict product fidelity checks (shape/buttons/logo layout) and reject over-stylized outputs.
- Confidence: **Medium** (official capability page + known production need).

---

## Outdated or underspecified instructions identified

1. Manual did not explicitly map when to use single-face lip sync vs multi-character lip sync.
2. Manual did not include explicit 5-minute claim as optional mode with caution.
3. Export recovery sequence needed more deterministic steps.
4. Manual lacked a preflight plan/capacity check despite plan-sensitive video limits.

---

## Concrete manual changes applied today

Updated `agents/knowledge/dzine_operator_manual.md` to include:

- **Preflight Check (new)**: plan/credits/concurrency/upscale verification.
- **Lip Sync Mode Selection (new)**: single-face default vs multi-character route (2–4 faces).
- **Segment policy update**: 45–90s default + optional long-form (up to 5 min claim, medium confidence).
- **Export recovery checklist expanded**: results click → editor/canvas active layer → retry export.
- **Product fidelity gate strengthened**: silhouette/control/logo placement consistency checks.

---

## Recommended next validation cycle (tomorrow)

1. Run controlled A/B for lip sync chunking:
   - A: 60–90s segments
   - B: 180–300s segments
   - Compare: mouth drift, transition smoothness, retake cost, total generation time.
2. Run 4-face multilingual micro-scene to verify claimed reliability in our stack.
3. Log plan consumption per successful minute exported to refine cost model.

---

## Study verdict

Manual update is justified by evidence and applied.
Most impactful immediate improvement: **preflight plan check + stricter export recovery path + explicit mode routing for multi-character scenes**.
