# RayViewsLab Channel Ops

Automated YouTube "Top 5" product review video pipeline. From trend scanning to published video.

Workspace boundary: this repo is the source of truth for channel automation.
If you also use `/Users/ray/Documents/openclaw`, see `/Users/ray/Documents/Rayviews/WORKSPACE_BOUNDARY.md`.

## Pipeline Overview

```
init-run (category selection)
    |
discover-products (Amazon scraping)
    |
generate-script (AI agents)
    |
[GATE 1] -- human approval (script + product list)
    |
generate-assets (Dzine image prompts)
    |
generate-voice (ElevenLabs voiceover)
    |
build-davinci (DaVinci timeline manifest)
    |
validate-originality (anti-inauthentic contract)
    |
validate-compliance (FTC/Amazon contract)
    |
[GATE 2] -- human approval (visuals + audio)
    |
render-and-upload (DaVinci render + YouTube)
    |
collect-metrics (24h performance)
    |
plan-variations (format variation engine, optional)
    |
convert-to-rayvault (RayVault conversion, optional)
```

## Project Structure

```
.
├── agents/          # AI agent configs, workflows, team roles
├── api/             # Vercel serverless endpoints (control plane)
│   ├── health.js
│   └── ops/         # heartbeat, summary, runs, gate, go
├── config/          # Category configs, trend queries, env examples
├── pipeline_runs/   # Canonical run artifacts (file-driven pipeline)
├── content/         # Legacy generated outputs (gitignored)
├── data/            # CSV templates
├── ops/             # Ops state files, runbooks, legacy n8n exports
├── reports/         # Generated trend/market/analysis reports
├── supabase/        # SQL migrations (001-005)
├── tests/           # Auth + sync tests
└── tools/           # Python & shell automation scripts
    └── lib/         # Shared utilities
```

## Setup

### Prerequisites

- Python 3.11+ (3.12 recommended)
- Node.js 18+ (for Vercel functions)
- ffmpeg / ffprobe (for asset processing and voiceover QC)
- DaVinci Resolve Studio (for video editing automation)
- beautifulsoup4 (Amazon scraping)
- playwright (lazy fallback for headless browsing)
- google-api-python-client (YouTube Data API v3)

### Install Python dependencies (macOS / Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

### Install Python dependencies (Windows PowerShell)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `python` opens Microsoft Store, disable App execution aliases for `python.exe` / `python3.exe` in Windows Settings and use `py -3.11`.

### Environment variables

Copy the example files and fill in your credentials:

```bash
cp config/supabase.env.example ~/.config/newproject/supabase.env
cp config/youtube.env.example ~/.config/newproject/youtube.env
```

Required env vars for Vercel deployment:

| Variable                    | Purpose                              |
| --------------------------- | ------------------------------------ |
| `SUPABASE_URL`              | Supabase project URL                 |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (never publishable) |
| `CRON_SECRET`               | Heartbeat cron authentication        |
| `OPS_READ_SECRET`           | Read access (summary/runs)           |
| `OPS_GATE_SECRET`           | Gate approval decisions              |
| `OPS_GO_SECRET`             | Final render/upload trigger          |

Optional env vars for Telegram notifications:

| Variable                            | Purpose                                                             |
| ----------------------------------- | ------------------------------------------------------------------- |
| `TELEGRAM_CHAT_ID`                  | Telegram target chat/user/channel                                   |
| `OPENCLAW_TELEGRAM_ACCOUNT`         | OpenClaw Telegram account id (default `tg_main`)                    |
| `TELEGRAM_USE_MINIMAX`              | Set `1` to rewrite alert messages with MiniMax before sending       |
| `MINIMAX_API_KEY`                   | MiniMax API key (also read from `~/.config/newproject/minimax.env`) |
| `MINIMAX_MODEL`                     | Optional model override (default `MiniMax-M2.5`)                    |
| `TELEGRAM_MINIMAX_TEMPLATE_DEFAULT` | Optional default rewrite system prompt                              |
| `TELEGRAM_MINIMAX_TEMPLATE_GATE`    | Optional rewrite template for gate notifications                    |
| `TELEGRAM_MINIMAX_TEMPLATE_FAILURE` | Optional rewrite template for failure alerts                        |
| `TELEGRAM_MINIMAX_TEMPLATE_SUMMARY` | Optional rewrite template for summaries                             |
| `TELEGRAM_REWRITE_LOG_PATH`         | Optional JSONL log file path for raw/rewritten Telegram messages    |
| `TELEGRAM_LOG_MESSAGES`             | Set `1` to force logging even without MiniMax rewrite               |

### Supabase setup

Apply migrations in order:

```bash
# In Supabase SQL Editor:
supabase/sql/001_ops_core.sql
supabase/sql/002_ops_hardening.sql
supabase/sql/003_ops_video_runs.sql
supabase/sql/004_ops_video_runs_locking.sql
supabase/sql/005_ops_step_locks.sql
```

## Usage

### Daily workflow (canonical: `tools/pipeline.py`)

```bash
# 1) Start run (or let run-e2e create one)
python3 tools/pipeline.py init-run \
  --category "portable_monitors" \
  --affiliate-tag "rayviews-20" \
  --tracking-id-override "rayviews-video001-20"

# 2) Build Gate 1 package (discovery + script). This stops for approval.
python3 tools/pipeline.py run-e2e --run-id "portable_monitors_2026-02-16_1254"

# 3) Human decision for Gate 1
python3 tools/pipeline.py approve-gate1 --run-id "portable_monitors_2026-02-16_1254" --reviewer "Ray" --notes "GO"
# (or reject)
# python3 tools/pipeline.py reject-gate1 --run-id "portable_monitors_2026-02-16_1254" --reviewer "Ray" --notes "Rewrite hook"

# 4) Build Gate 2 package (assets + voice + davinci plan). Stops again.
python3 tools/pipeline.py run-e2e --run-id "portable_monitors_2026-02-16_1254"

# Optional manual checks (already included in run-e2e gate2 package):
python3 tools/pipeline.py validate-originality --run-id "portable_monitors_2026-02-16_1254"
python3 tools/pipeline.py validate-compliance --run-id "portable_monitors_2026-02-16_1254"

# 5) Human decision for Gate 2
python3 tools/pipeline.py approve-gate2 --run-id "portable_monitors_2026-02-16_1254" --reviewer "Ray" --notes "GO"

# 6) Render + Upload (requires YouTube OAuth client secrets)
python3 tools/pipeline.py render-and-upload \
  --run-id "portable_monitors_2026-02-16_1254" \
  --youtube-client-secrets "/ABS/path/client_secret.json" \
  --tracking-id-override "rayviews-video001-20" \
  --privacy-status private
```

### OpenClaw stability guardrails (important)

When the Mac gets slow, the usual cause is an OpenClaw process storm (many orphaned `openclaw` processes).

```bash
# 1) Inspect (dry-run)
tools/openclaw_recover.sh

# 2) Recover orphans + restart managed browser service
tools/openclaw_recover.sh --apply --restart-browser
```

Additional protections already in place:

- `tools/chatgpt_ui.py` now serializes `openclaw browser` commands with a lock file.
- ChatGPT response wait now uses one `wait` call (with fallback), instead of high-frequency command polling.
- OpenClaw browser command calls include hard timeout protection.

If you use Claude Code on this repo, enforce:

- never run parallel loops that call `openclaw browser evaluate/tabs/status` every 1s.
- prefer one `wait` command with explicit timeout for UI readiness and output completion.
- before large runs, check process pressure and run `tools/openclaw_recover.sh` if needed.

### Telegram smoke test (control plane + optional MiniMax)

```bash
python3 tools/test_telegram_path.py --kind gate
python3 tools/test_telegram_path.py --kind summary
python3 tools/test_telegram_path.py --dry-run
```

### Legacy flow

`tools/top5_video_pipeline.py` re-exports shared symbols from `tools/video_pipeline_lib.py` and retains gate/state/writer logic.
`tools/pipeline_orchestrator.py` is a deprecated wrapper.
All new automation should target `tools/pipeline.py`.

### Run artifacts

Each run produces a structured directory under `pipeline_runs/<run_id>/`:

```
run.json                    # Run state and metadata
products.json               # Discovered products (contract schema)
products.csv                # Tabular export for review
discovery_receipt.json      # Discovery attempts (rate-limit/ban/fallback audit)
script.json                 # Structured script (segments)
security/input_guard_report.json # External input scan report for script generation
assets_manifest.json        # Image asset inventory
voice/timestamps.json       # Voice timing manifest
davinci/project.json        # DaVinci timeline plan
ops_tier_report.json        # Operational tier decision (normal/low_compute/critical/paused)
receipts/*.json             # Per-step receipts (inputs_hash, outputs_hash, timings, host/tools)
logs/*.jsonl                # Structured step logs
run_summary.json            # Aggregated run status
upload/youtube_url.txt      # Published video URL
metrics/metrics.json        # Performance snapshot
```

### Trend scanning

```bash
# Single query
python3 tools/youtube_trends.py --query "portable monitor review" --out reports/trends/portable_monitors.json

# Batch (all configured queries)
python3 tools/youtube_trends_batch.py

# Generate market pulse from trends
python3 tools/market_pulse_from_trends.py
```

### Ops management

```bash
# Propose a new mission
python3 tools/ops_loop.py propose --title "Open-ear earbuds Top 5" --category "audio"

# List missions
python3 tools/ops_loop.py list

# Sync to Supabase
python3 tools/supabase_sync_ops.py
```

### Distributed execution (Mac ↔ Windows)

See `/Users/ray/Documents/Rayviews/README_CLUSTER.md` for Tailscale setup, worker startup, controller health checks, and remote job submission.

## API Endpoints (Vercel)

| Endpoint             | Method   | Auth              | Purpose                |
| -------------------- | -------- | ----------------- | ---------------------- |
| `/api/health`        | GET      | None              | Health check           |
| `/api/ops/heartbeat` | GET/POST | `CRON_SECRET`     | Daily heartbeat        |
| `/api/ops/summary`   | GET      | `OPS_READ_SECRET` | Table counts           |
| `/api/ops/runs`      | GET      | `OPS_READ_SECRET` | Video run status       |
| `/api/ops/gate`      | POST     | `OPS_GATE_SECRET` | Approve/reject gates   |
| `/api/ops/go`        | POST     | `OPS_GO_SECRET`   | Advance pipeline state |

## Tests

```bash
# API auth tests
node --test tests/control_plane_auth.test.js

# Supabase sync validation
python3 -m pytest tests/test_supabase_sync_ops.py
```

## Quality Gates

All videos pass through two mandatory human approval gates before any paid resources (voiceover, rendering) are consumed:

- **Gate 1**: Product selection, pricing accuracy, script review, claim verification
- **Gate 2**: Visual assets, voiceover quality, storyboard approval

### Automatic contracts before Gate 1

- `generate-script` now writes `security/input_guard_report.json`
  - scans untrusted product fields for injection-like patterns.
  - `critical` blocks script generation and Gate 1 approval.
  - `high` sets Gate 1 to WARN mode; approval requires `--notes "#override-warn ..."`.

### Automatic contracts before Gate 2

- `validate-originality` writes `originality_report.json`
  - checks script uniqueness score, template phrase repetition, evidence segments per product, opinion density.
- `validate-compliance` writes `compliance_report.json`
  - enforces disclosure contract (intro + description + pinned comment),
  - validates affiliate link clarity (blocks external shorteners, allows first-party `amzn.to`),
  - patches manifest with compliance block when available.
- `ops_tier_report.json` is recomputed before Gate 2 / render
  - derives runtime tier from budget + failure pressure.
  - `critical` / `paused` blocks expensive steps (assets, voice, DaVinci, render/upload).
- `render_inputs` contract is now part of Gate 2 auto-check
  - requires `voice/voiceover.mp3`,
  - requires all required Dzine image variants from `assets_manifest.json`,
  - requires `davinci/render_ready.flag`.

Gate 2 approval is blocked if any automatic contract is `FAIL`.
If a contract is `WARN`, approval requires `--notes "#override-warn ..."` to acknowledge risk.

### Format moat (editorial differentiation)

`variation_plan.json` now rotates an `editorial_format` dimension to avoid generic repeated structure:

- `classic_top5`
- `buy_skip_upgrade`
- `persona_top3`
- `one_winner_two_alts`
- `budget_vs_premium`

Policy is configurable in `/Users/ray/Documents/Rayviews/policies/format_variation_policy.json`.

See `ops/QUALITY_FIRST_RUNBOOK.md` for the full runbook.
