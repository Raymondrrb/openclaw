# HEARTBEAT.md - DaVinci Editor

On heartbeat:

1. Find latest episode folder in `/Users/ray/Documents/Rayviews/content/`.
2. Read `/Users/ray/Documents/Rayviews/agents/knowledge/davinci_operator_manual.md` before editing (if exists).
3. If `script_long.md` exists and `davinci_edit_plan.md` is missing, generate full edit pack.
4. Ensure `davinci_qc_checklist.md` includes audio loudness + compliance checks.
5. If `quality_gate.md` is FAIL, create `davinci_fix_pass.md` with top corrections.
6. If nothing actionable, reply `HEARTBEAT_OK`.
