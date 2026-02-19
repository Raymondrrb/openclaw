# Workflow: DaVinci Deep Study

Goal: continuously improve DaVinci editing quality and operational speed.

## Inputs

- Current manual: `agents/knowledge/davinci_operator_manual.md`
- Latest episode outputs in `content/<slug>/`
- DaVinci official docs/release notes pages (when reachable)
- QC issues from recent runs

## Outputs

- `reports/davinci/TODAY_davinci_deep_study.md`
- `reports/davinci/TODAY_davinci_experiments.md`
- Updates to `agents/knowledge/davinci_operator_manual.md`

## Study Procedure

1. Collect official updates relevant to Edit/Fairlight/Color/Deliver.
2. Identify which current rules are outdated or underspecified.
3. Run 3 focused experiments:
   - pacing & retention cadence,
   - VO/music intelligibility chain,
   - export reliability and render time.
4. Record measured outcomes and winning settings.
5. Update manual and templates with evidence-backed changes.

## Hard Rules

- No feature claims without evidence.
- Confidence labels (high/medium/low) per finding.
- Keep recommendations executable in Ray's current stack.
