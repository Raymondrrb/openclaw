# RayViews Boundary Note

This OpenClaw repo and `/Users/ray/Documents/Rayviews` are related but not identical.

## Use this repo for

- OpenClaw runtime/gateway/channel internals.
- Agent platform/core behavior.

## Use `/Users/ray/Documents/Rayviews` for

- YouTube channel pipeline orchestration.
- Gate1/Gate2 workflow, Vercel control-plane endpoints, Supabase ops tables.
- Daily run artifacts and channel operation scripts.

## Cross-repo sync policy

Only sync shared glue files intentionally. Current shared set:

- `tools/chatgpt_ui.py`
- `tests/test_chatgpt_ui.py`
- `tools/openclaw_recover.sh`

Reference sync command (from Rayviews repo):

```bash
/Users/ray/Documents/Rayviews/tools/sync_with_openclaw.sh --to-openclaw --apply
```
