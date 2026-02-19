# HEARTBEAT.md - Dzine Producer

On heartbeat:

1. Find latest episode folder in `/Users/ray/Documents/Rayviews/content/`.
2. Read `/Users/ray/Documents/Rayviews/agents/knowledge/dzine_operator_manual.md` before execution (if exists).
3. If `quality_gate.md` is PASS and `dzine_generation_report.md` is missing, generate Dzine pack.
4. Ensure `dzine_thumbnail_candidates.md` exists (3-5 options) for CTR test.
5. If blocked by auth/captcha, write `dzine_blockers.md`.
6. If nothing actionable, reply `HEARTBEAT_OK`.
