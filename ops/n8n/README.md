# n8n Gate Control (Import)

## File

- `/Users/ray/Documents/Rayviews/ops/n8n/RayViews_Gate_Control.workflow.json`

## What it does

- Receives `POST` webhook at `rayviews/gate-decision`
- Calls `POST /api/ops/gate`
- If `gate=gate2` and `decision=approve`, also calls `POST /api/ops/go` with `action=start_render`
- Returns JSON response to caller

## Required n8n Variables

Create these in n8n Variables before activating:

- `OPS_GATE_SECRET`
- `OPS_GO_SECRET`

## Webhook payload example

```json
{
  "run_slug": "portable_monitors_2026-02-09",
  "gate": "gate2",
  "decision": "approve",
  "reviewer": "Ray",
  "notes": "GO from Telegram"
}
```

## Expected behavior

- `gate1` approve/reject -> records gate and responds
- `gate2` approve -> records gate, sends GO render, responds
- `gate2` reject -> records gate and responds without GO

## Note about webhook responses

If your production webhook is returning HTTP 200 with an empty body (`content-length: 0`),
edit both `Respond gate-only` and `Respond gate+go` nodes and set:

- Respond With: `JSON`
- Response Body (Expression): `{{$json}}`

Then `Publish` again. Production webhooks run the last published version.
