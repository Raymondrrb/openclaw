# Vercel Setup (Control Plane Only)

Goal: use Vercel for lightweight control endpoints and heartbeat logging into Supabase.

Scope:

- `GET /api/health`
- `GET|POST /api/ops/heartbeat` (writes `ops_agent_events`)
- `GET /api/ops/summary` (reads ops counts)
- `GET /api/ops/runs` (latest video runs for GO/NO-GO inbox)
- `POST /api/ops/gate` (approve/reject gate1 or gate2)
- `POST /api/ops/go` (advance state after gate2 approval: render/upload/publish)
- Daily cron -> `/api/ops/heartbeat` at `12:10 UTC` (`09:10` Sao Paulo)

## 1) Connect project on Vercel

1. Open Vercel Dashboard -> **Add New...** -> **Project**.
2. Import GitHub repo: `Raymondrrb/rayviewslab-channel-ops`.
3. If the private repo does not appear:
   - In Vercel, go to **Settings -> Git -> Manage GitHub App**.
   - Ensure the Vercel GitHub app has access to `rayviewslab-channel-ops` (or set to all repositories).
   - Return to Vercel Import page and click **Refresh**.
4. Framework preset: **Other**.
5. Root Directory: repository root (`/`).
6. Click **Deploy**.

## 2) Add environment variables (Project -> Settings -> Environment Variables)

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `CRON_SECRET` (required for `/api/ops/heartbeat` and Vercel Cron auth)
- `OPS_CRON_SECRET` (optional; for local tooling compatibility. If set, keep it equal to `CRON_SECRET`.)
- `OPS_READ_SECRET` (required)
- `OPS_GATE_SECRET` (required for `/api/ops/gate`)
- `OPS_GO_SECRET` (required for `/api/ops/go`; do not rely on fallback)

Notes:

- Use Supabase **secret/service_role** key, never publishable key.
- Keep same values for Production (and Preview only if needed).

## 3) Redeploy

After adding env vars, run **Redeploy** once.

## 4) Smoke tests

Replace `<your-vercel-domain>` with your deployment URL.

Health:

```bash
curl -s "https://<your-vercel-domain>/api/health"
```

Heartbeat (manual trigger):

```bash
curl -s -H "Authorization: Bearer <CRON_SECRET>" \
  "https://<your-vercel-domain>/api/ops/heartbeat"
```

Summary:

```bash
curl -s -H "Authorization: Bearer <OPS_READ_SECRET>" \
  "https://<your-vercel-domain>/api/ops/summary"
```

Latest runs:

```bash
curl -s -H "Authorization: Bearer <OPS_READ_SECRET>" \
  "https://<your-vercel-domain>/api/ops/runs?limit=5"
```

Gate decision:

```bash
curl -s -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <OPS_GATE_SECRET>" \
  -d '{"run_slug":"portable_monitors_2026-02-09","gate":"gate2","decision":"approve","reviewer":"Ray","notes":"GO"}' \
  "https://<your-vercel-domain>/api/ops/gate"
```

GO action:

```bash
curl -s -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <OPS_GO_SECRET>" \
  -d '{"run_slug":"portable_monitors_2026-02-09","action":"start_render","requested_by":"Ray","notes":"GO after gate2"}' \
  "https://<your-vercel-domain>/api/ops/go"
```

## 5) Confirm cron is active

1. Vercel Dashboard -> Project -> **Settings** -> **Cron Jobs**.
2. Confirm one job exists: `/api/ops/heartbeat`.
3. Wait next run or click manual trigger if available.

## 6) Optional: tighten schedule

Current default is once per day (`10 12 * * *` UTC).
If you want another time, edit `/vercel.json` and redeploy.

## 7) Keep responsibilities split (recommended)

- Vercel: control plane APIs, cron trigger, dashboards.
- Local Mac/VPS + OpenClaw: browser sessions, Dzine, Amazon affiliate extraction, DaVinci automation.
