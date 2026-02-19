# n8n Control Layer (Quality-First)

Use n8n as control/alert layer only:

- GO/NO-GO human approval
- failure alerts
- daily executive logging

Keep OpenClaw as executor and Supabase as source of truth.

## Required endpoints (already in this repo)

- `GET /api/health`
- `GET /api/ops/summary`
- `GET /api/ops/runs?limit=5`
- `POST /api/ops/gate`
- `POST /api/ops/go`

## Required env vars on Vercel

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `CRON_SECRET`
- `OPS_READ_SECRET`
- `OPS_GATE_SECRET`
- `OPS_GO_SECRET` (required; you may set it equal to `OPS_GATE_SECRET`, but separation is recommended)

## Workflow 1: Daily GO/NO-GO (Telegram)

1. Trigger: `Cron` at 09:05 (America/Sao_Paulo).
2. Node: `HTTP Request` -> `GET /api/ops/runs?limit=1` with `Authorization: Bearer <OPS_READ_SECRET>`.
3. Node: `Code` (or Set) -> build concise message:
   - run slug, category
   - gate status
   - latest status (`draft_ready_waiting_gate_1` or `assets_ready_waiting_gate_2`)
4. Node: `Telegram` send message with buttons:
   - `GO Gate1`
   - `NO Gate1`
   - `GO Gate2`
   - `NO Gate2`
5. Node: `Webhook` (callback) receives button payload.
6. Node: `HTTP Request` -> `POST /api/ops/gate` with `Authorization: Bearer <OPS_GATE_SECRET>`.
   Body example:
   ```json
   {
     "run_slug": "portable_monitors_2026-02-09",
     "gate": "gate2",
     "decision": "approve",
     "reviewer": "Ray",
     "notes": "GO from Telegram"
   }
   ```
7. If `gate=gate2` and `decision=approve`, call:
   - `POST /api/ops/go` with `Authorization: Bearer <OPS_GO_SECRET>`
   - body:
   ```json
   {
     "run_slug": "portable_monitors_2026-02-09",
     "action": "start_render",
     "requested_by": "Ray",
     "notes": "Gate2 approved from Telegram"
   }
   ```

## Workflow 2: Failure alert

1. Trigger: `Cron` every 10 minutes.
2. Node: `HTTP Request` -> `GET /api/ops/runs?limit=10&status=failed`.
3. Node: IF `count > 0`.
4. Node: Telegram/Email alert with run slug + updated_at.

## Workflow 3: Executive daily log

1. Trigger: `Cron` at 21:30.
2. Node: `HTTP Request` -> `/api/ops/summary`.
3. Node: `HTTP Request` -> `/api/ops/runs?limit=20`.
4. Node: write row in Sheets/Notion:
   - date
   - total runs
   - published/failed counts
   - latest run slug/status

## Security

- Do not expose `OPS_GATE_SECRET` to client-side code.
- Do not expose `OPS_GO_SECRET` to client-side code.
- Use n8n credential store for bearer tokens.
- Keep `OPS_READ_SECRET`, `OPS_GATE_SECRET`, and `OPS_GO_SECRET` different.

## Operational rule

- No `gate2=approve` => no publish.
- No `GO start_render` => no render/upload state transition.
- Render/upload remains blocked by the state machine in `/Users/ray/Documents/Rayviews/tools/pipeline.py` (quality gates in run.json).
