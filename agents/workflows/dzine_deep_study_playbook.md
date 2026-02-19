# Workflow: Dzine Deep Study

Goal: continuously improve Dzine operation quality and document repeatable best practices.

## Inputs

- Current operator manual: `agents/knowledge/dzine_operator_manual.md`
- Latest episode artifacts in `content/<slug>/`
- Official Dzine docs/help center pages (when reachable)
- In-app observations from real runs

## Outputs

- `reports/dzine/TODAY_dzine_deep_study.md`
- Update `agents/knowledge/dzine_operator_manual.md`
- `reports/dzine/TODAY_dzine_experiments.md`

## Study Procedure

1. Collect official updates (features, limits, export modes, lip sync options).
2. Compare against current manual and identify outdated instructions.
3. Run 3 focused experiments:
   - Lip sync smoothness settings
   - Product reference fidelity
   - Thumbnail CTR framing patterns
4. Record measured outcomes and select winners.
5. Apply concrete updates to operator manual and prompt templates.

## Hard Rules

- Do not invent feature claims without evidence.
- Mark confidence (high/medium/low) per finding.
- Keep recommendations executable in Ray's current stack.
