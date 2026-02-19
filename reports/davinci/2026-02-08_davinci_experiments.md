# DaVinci Experiments — 2026-02-08

## Experiment 1 — Pacing & Retention Cadence

- Goal: Reduce viewer drop risk in ranked segments.
- Hypothesis: Enforcing a hard cadence ceiling (no unintended >5s static visuals, with beat-anchor candidates where music exists) improves perceived momentum.
- Method:
  1. Use timeline map block boundaries as hard chapter cuts.
  2. During Cut-page speed pass, scan for >5s static zones.
  3. If music-backed section exists, run AI Detect Music Beats and test cut anchoring on 1 block.
- Success Metrics:
  - 0 unintended >5s static zone in ranked blocks.
  - Product visible in first 2s for each product segment.
  - Manual reviewer reports “no pacing stalls”.
- Result (artifact-based today):
  - Cadence rules are present and repeatedly reinforced in plans/checklists.
  - No measured playback audit performed in Resolve today.
- Outcome: **Provisional Pass (process-level)**
- Confidence: **Medium**

## Experiment 2 — VO/Music Intelligibility Chain

- Goal: Improve speech clarity while avoiding peak-related distortion.
- Hypothesis: Adding a pre-Fairlight VO ingest gate (peak <= -1.0 dBTP equivalent safety margin) plus standard ducking chain lowers intelligibility failures.
- Method:
  1. Parse chunk-level voice report before timeline build.
  2. Route flagged chunks to normalization/re-render path before final mix.
  3. Apply preferred chain: AI Audio Assistant → Dialogue Separator → Ducker → EQ/Comp → De-esser (if needed) → Limiter.
- Success Metrics:
  - No chunk above peak safety threshold entering final timeline.
  - Final master target around -14 LUFS integrated, true peak <= -1.0 dBTP.
- Result (artifact-based today):
  - 3 chunks flagged above safety threshold in source report (`vo_04`, `vo_07`, `vo_09`).
  - Team already keeps normalized folder variants, indicating workable mitigation path.
- Outcome: **Pass with Required Gate Tightening**
- Confidence: **High**

## Experiment 3 — Export Reliability & Render Time

- Goal: Reduce failed exports and avoid publish-time surprises.
- Hypothesis: Explicit proxy→original relink verification plus retry ladder reduces rerender churn and silent errors.
- Method:
  1. Keep proxy editing enabled for speed.
  2. Before final export, enforce relink validation + offline/clipping/black-frame/caption checks.
  3. On failure, use documented retry ladder before codec switch.
- Success Metrics:
  - Export succeeds on first or second attempt with preserved logs.
  - Zero offline media in final deliverable.
- Result (artifact-based today):
  - Reliability protocol exists in manual and export preset docs.
  - No fresh export failure logs detected in latest analyzed folders.
- Outcome: **Pass (procedural)**
- Confidence: **Medium-High**

## Net Changes Proposed from Experiments

1. Promote VO pre-ingest peak gate from implied practice to explicit hard gate.
2. Add metric-card parity check to prevent stale dynamic overlays.
3. Add quick audio triage path for flagged chunks to avoid late mix firefighting.

## Next Cycle

- Run one Resolve-in-the-loop measurement cycle with actual timeline loudness meter screenshots/log values to upgrade confidence on Experiment 1 and 3 from procedural to measured.
