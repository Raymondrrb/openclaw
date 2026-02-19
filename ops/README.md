# Ops Closed Loop (Local)

Purpose: Minimal closed-loop workflow without external infrastructure.

Default state directory (runtime):

- `~/.config/newproject/ops`
- Override with env var: `OPS_DIR=/custom/path`

Core files:

- policies.json: quotas and auto-approve rules
- proposals.json: incoming proposals
- missions.json: approved missions with steps
- events.jsonl: event log
- reactions.json: reaction patterns

Default step order:

- trend_scan -> research -> script -> assets -> seo -> edit -> review -> qa -> export -> upload

Common commands:

```
python3 /Users/ray/Documents/Rayviews/tools/ops_loop.py propose \
  --title "Open-ear earbuds Top 5" \
  --category "audio"

python3 /Users/ray/Documents/Rayviews/tools/ops_loop.py list

python3 /Users/ray/Documents/Rayviews/tools/ops_loop.py claim-step --mission-id MISSION_ID --step-id STEP_ID
python3 /Users/ray/Documents/Rayviews/tools/ops_loop.py complete-step --mission-id MISSION_ID --step-id STEP_ID
python3 /Users/ray/Documents/Rayviews/tools/ops_loop.py recover-stale
```

Optional Supabase persistence:

- Setup guide: `/Users/ray/Documents/Rayviews/ops/SUPABASE_SETUP.md`
- One-shot sync command:
  `python3 /Users/ray/Documents/Rayviews/tools/supabase_sync_ops.py`

Current mission (`mission_a7d03f29`) finalization:

```
python3 /Users/ray/Documents/Rayviews/tools/ops_loop.py complete-step --mission-id mission_a7d03f29 --step-id step_140265
python3 /Users/ray/Documents/Rayviews/tools/ops_loop.py complete-step --mission-id mission_a7d03f29 --step-id step_95df7e
```
