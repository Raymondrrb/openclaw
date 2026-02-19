# HEARTBEAT.md - Publisher

On heartbeat:

1. Find latest episode folder in `/Users/ray/Documents/Rayviews/content/`.
2. If `davinci_qc_checklist.md` exists and `publish_package.md` is missing, generate publish pack.
3. If `review_final.md` is NO-GO or `quality_gate.md` is FAIL, create `publish_blockers.md`.
4. If nothing actionable, reply `HEARTBEAT_OK`.
