# Vercel Repo Notes (Applied to This Project)

Source repo reviewed: https://github.com/vercel/vercel

## What matters for this project

1. Use Vercel as control plane, not media pipeline runner.

- Keep heavy workloads (OpenClaw browser automation, Dzine, ElevenLabs, DaVinci) local/VPS.
- Keep Vercel for lightweight API endpoints and cron triggers.

2. Protect cron auth headers correctly.

- Vercel CLI validates `CRON_SECRET` because it is sent as an HTTP header.
- Avoid leading/trailing whitespace and non-ASCII/control chars.
- We already use hex secrets, which are safe.

3. Keep Git connection explicit.

- Vercel CLI supports `vercel git connect` and `vercel git disconnect`.
- This is the safest way to fix wrong repo links quickly.

4. Use environment variables safely for automation.

- `VERCEL_TOKEN` env support exists in recent CLI versions (better for scripts/CI than passing `--token`).
- Keep secrets in local env files with strict permissions and do not commit them.

5. `vercel.json` options that are useful here.

- `github.autoJobCancelation`: true (cancel stale builds).
- `github.silent`: true (less PR noise).
- `functions.api/**/*.js.maxDuration`: keep small because endpoints are lightweight.
- `crons`: keep only heartbeat cadence needed.

6. Cache policy for control endpoints.

- For operational APIs (`/api/health`, `/api/ops/heartbeat`, `/api/ops/summary`), return `Cache-Control: no-store`.

## Changes applied now

1. Added `Cache-Control: no-store`:

- `/Users/ray/Documents/Rayviews/api/health.js`
- `/Users/ray/Documents/Rayviews/api/ops/heartbeat.js`
- `/Users/ray/Documents/Rayviews/api/ops/summary.js`

2. Added GitHub deploy behavior config:

- `/Users/ray/Documents/Rayviews/vercel.json`
  - `"github": { "silent": true, "autoJobCancelation": true }`

3. Added one-command control plane checker:

- `/Users/ray/Documents/Rayviews/tools/vercel_control_plane_check.sh`

## Command references used in this setup

```bash
# Connect correct repo
vercel git connect https://github.com/Raymondrrb/rayviewslab-channel-ops

# Check project
vercel project inspect new-project-control-plane

# Check env vars
vercel env ls

# Check control plane endpoints (local script)
zsh "/Users/ray/Documents/Rayviews/tools/vercel_control_plane_check.sh"
```
