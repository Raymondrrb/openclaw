# RayViewsLab Cluster (Mac Controller ↔ Windows Worker)

This adds a distributed execution layer for RayVault with **Tailscale** transport.

## What is implemented

- Protocol contract: `/Users/ray/Documents/Rayviews/rayvault/agent/protocol.py`
- Worker API (Windows): `/Users/ray/Documents/Rayviews/rayvault/agent/worker_server.py`
- Job executors: `/Users/ray/Documents/Rayviews/rayvault/agent/jobs.py`
- Controller (Mac): `/Users/ray/Documents/Rayviews/rayvault/agent/controller.py`
- Cluster config: `/Users/ray/Documents/Rayviews/state/cluster/nodes.json`
- Start scripts:
  - Windows worker: `/Users/ray/Documents/Rayviews/tools/cluster/start_worker.ps1`
  - Mac controller: `/Users/ray/Documents/Rayviews/tools/cluster/start_controller.sh`

## Security model

- Worker auth supports:
  - HMAC token (preferred)
  - plain token fallback (rotation / compatibility only)
- Controller defaults to `hmac_strict` mode.
- Controller secret env priority:
  - `RAYVAULT_CLUSTER_SECRET`
  - `RAYVAULT_CLUSTER_SECRET_CURRENT`
  - optional `RAYVAULT_CLUSTER_SECRET_PREVIOUS` for rotation grace period
- To temporarily allow plain fallback from controller, set:
  - `RAYVAULT_ALLOW_PLAIN_FALLBACK=1`
- Worker idempotency: same `step_name + inputs_hash` returns cached job.
- `OPENCLAW_TASK` runs only with active desktop session.
  - If no UI session: fails with `UI_SESSION_REQUIRED`.
- Do not expose secrets through download endpoints or query strings in shared logs.

## Supported worker jobs

- `TTS_RENDER_CHUNKS`
- `AUDIO_POSTCHECK`
- `FFMPEG_PROBE`
- `FRAME_SAMPLING`
- `OPENCLAW_TASK` (optional / UI only)

## Architecture rules

- Mac is **Controller** and mandatory owner of final DaVinci render.
- Windows is **Worker** for headless steps.
- If worker is unavailable, controller falls back to local execution.

## 1) Install Tailscale

### Mac

Option A (CLI):

```bash
brew install tailscale
```

Then run daemon with admin rights (required for system tunnel):

```bash
sudo tailscaled
sudo tailscale up
```

Option B (Desktop app): install Tailscale.app and login.

### Windows

- Install Tailscale app
- Sign in with same tailnet account

### Verify node IPs

On each machine:

```bash
tailscale ip -4
```

Use the `100.x.y.z` address in `state/cluster/nodes.json`.

## 2) Worker setup (Windows)

### Python deps

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `python` opens Microsoft Store, disable `python.exe` / `python3.exe` App execution aliases and use `py -3.11`.

### Env

```powershell
$env:RAYVAULT_CLUSTER_SECRET = "<strong-shared-secret>"
$env:RAYVAULT_WORKER_ID = "windows-worker-1"
$env:RAYVAULT_WORKER_PORT = "8787"
```

### Start worker bound to Tailscale IP

```powershell
./tools/cluster/start_worker.ps1 -Host "100.x.y.z" -Port 8787
```

Health check from Windows local:

```powershell
curl http://100.x.y.z:8787/health
```

## 3) Controller setup (Mac)

### Env

```bash
export RAYVAULT_CLUSTER_SECRET="<same-strong-shared-secret>"
# Optional rotation variable (preferred during secret rollout)
export RAYVAULT_CLUSTER_SECRET_CURRENT="<same-strong-shared-secret>"
```

### Configure node

Edit `/Users/ray/Documents/Rayviews/state/cluster/nodes.json`:

- Set `host` to Windows Tailscale IP
- Set `enabled: true` for the worker

### Health check

```bash
/Users/ray/Documents/Rayviews/tools/cluster/start_controller.sh health
```

### Probe capabilities

```bash
/Users/ray/Documents/Rayviews/tools/cluster/start_controller.sh caps
```

The worker `/caps` response now includes normalized capability keys used by scheduling:
`os`, `cpu`, `ram_gb`, `gpu_model`, `vram_gb`, `python_version`, `ffmpeg_version`, `davinci_available`.

### Sync artifacts for an existing remote job

```bash
/Users/ray/Documents/Rayviews/tools/cluster/start_controller.sh sync-artifacts \
  --run-id cluster_smoke_001 \
  --job-id ffprobe_001 \
  --node-id windows-worker-1
```

## 4) Submit a test job from Mac

```bash
/Users/ray/Documents/Rayviews/tools/cluster/start_controller.sh submit \
  --run-id cluster_smoke_001 \
  --job-id ffprobe_001 \
  --step-name FFMPEG_PROBE \
  --payload-json '{"media_path":"/path/to/video.mp4"}' \
  --requirements-json '{"os_in":["windows"],"min_ram_gb":8}'
```

Receipt output is written to:

- `/Users/ray/Documents/Rayviews/state/cluster/receipts/<run_id>/<job_id>/job_receipt.json`
- `/Users/ray/Documents/Rayviews/state/cluster/receipts/<run_id>/<job_id>/worker.log`

## Firewall guidance

- Do not expose worker on LAN/WAN.
- Bind worker only to Tailscale IP (or localhost for local-only).
- Allow inbound port `8787` only for Tailscale interface.

## Troubleshooting

- `401 auth_token invalid`:
  - secrets differ between Mac and Windows, or clock skew too large.
- `timestamp outside allowed skew`:
  - sync system clocks (NTP).
- `UI_SESSION_REQUIRED`:
  - `OPENCLAW_TASK` requested without active logged-in desktop session.
- Worker unreachable:
  - verify both nodes are online in Tailscale and that worker bound to correct `100.x` IP.

## Compatibility note

If controller output shows `"_compat_mode": "legacy_hmac_v05"` (or `legacy_plain_token`) in `caps`, the Windows node is running the v0.5 worker contract.

- Connectivity/auth is OK.
- Job delegation may still fallback local if remote capabilities do not include RayVault step names
  (`TTS_RENDER_CHUNKS`, `AUDIO_POSTCHECK`, `FFMPEG_PROBE`, `FRAME_SAMPLING`, `OPENCLAW_TASK`).
- Controller currently maps these names for legacy workers:
  - `TTS_RENDER_CHUNKS` -> `tts_render_chunks`
  - `AUDIO_POSTCHECK` -> `audio_postcheck`
  - `FFMPEG_PROBE` -> `ffprobe_analyze`
  - `FRAME_SAMPLING` -> `frame_sampling`
  - `OPENCLAW_TASK` -> `openclaw_task`

To enable full distributed execution for those steps, run the worker from this repo (`python -m rayvault.agent.worker_server`) on Windows.
