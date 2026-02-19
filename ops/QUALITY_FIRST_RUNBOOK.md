# Quality-First Pipeline Runbook (No n8n Required)

Canonical executor: `tools/pipeline.py`

## Pipeline steps

1. `init-run` — create run directory and config
2. `discover-products` — Amazon scraping + product selection
3. `generate-script` — structured JSON script via LLM
4. **GATE 1** — human approval (script + product list)
5. `generate-assets` — Dzine image prompts + reference images
6. `generate-voice` — ElevenLabs voice segments
7. `build-davinci` — DaVinci Resolve timeline manifest
8. **GATE 2** — human approval (visuals + audio + timeline)
9. `render-and-upload` — DaVinci render + YouTube upload
10. `collect-metrics` — 24h performance snapshot
11. `plan-variations` — format variation engine (optional)
12. `convert-to-rayvault` — RayVault conversion (optional)

Hard rule: `render-and-upload` is blocked unless Gate 2 is approved.

## 0) One-time setup

1. Apply Supabase migrations:

- `/Users/ray/Documents/Rayviews/supabase/sql/001_ops_core.sql`
- `/Users/ray/Documents/Rayviews/supabase/sql/002_ops_hardening.sql`
- `/Users/ray/Documents/Rayviews/supabase/sql/003_ops_video_runs.sql`
- `/Users/ray/Documents/Rayviews/supabase/sql/004_ops_video_runs_locking.sql`

2. Configure secrets in env files (`~/.config/newproject/*.env`):

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `MINIMAX_API_KEY` (or use `--source openclaw`)
- `ELEVENLABS_API_KEY` (optional if generating real TTS)

## 1) Gate 1 package (STOP)

```bash
python3 /Users/ray/Documents/Rayviews/tools/pipeline.py init-run \
  --category "portable_monitors" \
  --affiliate-tag "rayviews-20"

python3 /Users/ray/Documents/Rayviews/tools/pipeline.py run-e2e \
  --run-id "portable_monitors_2026-02-16_1254"
```

Review:

- `pipeline_runs/<run_id>/products.json`
- `pipeline_runs/<run_id>/products.csv`
- `pipeline_runs/<run_id>/script.json`

Approve/reject:

```bash
python3 /Users/ray/Documents/Rayviews/tools/pipeline.py approve-gate1 \
  --run-id "portable_monitors_2026-02-16_1254" \
  --reviewer "Ray" \
  --notes "GO"
```

```bash
python3 /Users/ray/Documents/Rayviews/tools/pipeline.py reject-gate1 \
  --run-id "portable_monitors_2026-02-16_1254" \
  --reviewer "Ray" \
  --notes "Rewrite intro and claims"
```

## 2) Gate 2 package (STOP)

```bash
python3 /Users/ray/Documents/Rayviews/tools/pipeline.py run-e2e \
  --run-id "portable_monitors_2026-02-16_1254"
```

Review:

- `pipeline_runs/<run_id>/assets_manifest.json`
- `pipeline_runs/<run_id>/voice/timestamps.json`
- `pipeline_runs/<run_id>/davinci/project.json`
- `pipeline_runs/<run_id>/rayvault/05_render_config.json`

Approve/reject:

```bash
python3 /Users/ray/Documents/Rayviews/tools/pipeline.py approve-gate2 \
  --run-id "portable_monitors_2026-02-16_1254" \
  --reviewer "Ray" \
  --notes "GO"
```

```bash
python3 /Users/ray/Documents/Rayviews/tools/pipeline.py reject-gate2 \
  --run-id "portable_monitors_2026-02-16_1254" \
  --reviewer "Ray" \
  --notes "Regenerate product 2 visuals"
```

## 3) Render + upload

```bash
python3 /Users/ray/Documents/Rayviews/tools/pipeline.py render-and-upload \
  --run-id "portable_monitors_2026-02-16_1254" \
  --youtube-client-secrets "/ABS/path/client_secret.json" \
  --privacy-status private \
  --step-retries 3 \
  --step-backoff-sec 8
```

Outputs:

- `pipeline_runs/<run_id>/rayvault/publish/video_final.mp4`
- `pipeline_runs/<run_id>/upload/youtube_video_id.txt`
- `pipeline_runs/<run_id>/upload/youtube_url.txt`
- `pipeline_runs/<run_id>/upload/youtube_upload_report.json`

## 4) Status and metrics

```bash
python3 /Users/ray/Documents/Rayviews/tools/pipeline.py status --run-id "portable_monitors_2026-02-16_1254"
python3 /Users/ray/Documents/Rayviews/tools/pipeline.py collect-metrics --run-id "portable_monitors_2026-02-16_1254"
```

## Notes

- `tools/pipeline_orchestrator.py` is a legacy wrapper (deprecated).
- `tools/top5_video_pipeline.py` re-exports shared symbols from `video_pipeline_lib.py` and contains gate/state/writer logic.
- `tools/video_pipeline_lib.py` is the shared library (data models, scrapers, script generation).
- Do not use n8n as executor. If used, keep it only as optional trigger/notification.

## Individual step debugging

```bash
# Run a single step:
python3 tools/pipeline.py discover-products --run-id RUN_ID
python3 tools/pipeline.py generate-script --run-id RUN_ID
python3 tools/pipeline.py generate-assets --run-id RUN_ID
python3 tools/pipeline.py generate-voice --run-id RUN_ID
python3 tools/pipeline.py build-davinci --run-id RUN_ID

# Check run status:
python3 tools/pipeline.py status --run-id RUN_ID
```
