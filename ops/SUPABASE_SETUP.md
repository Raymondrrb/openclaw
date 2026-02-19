# Supabase Setup (Ops + Agents)

Objective: keep your current local OpenClaw workflow, but persist operational state in Supabase for durability and dashboard queries.

State path used for background sync:

- `~/.config/newproject/ops` (avoids macOS background access issues with `Documents/`)

## 1) Create tables in Supabase

1. Open Supabase Dashboard -> SQL Editor.
2. Run (in this order):

- `/Users/ray/Documents/Rayviews/supabase/sql/001_ops_core.sql`
- `/Users/ray/Documents/Rayviews/supabase/sql/002_ops_hardening.sql`

## 2) Configure environment variables

Use this template:
`/Users/ray/Documents/Rayviews/config/supabase.env.example`

In terminal (same session where you run scripts):

```bash
export SUPABASE_URL="https://YOUR_PROJECT_ID.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="YOUR_SERVICE_ROLE_KEY"
export SUPABASE_SCHEMA="public"
```

Important:

- Use `Service Role` / `Secret` key only for backend sync.
- Do not use publishable/anon key in these scripts.

Optional (recommended): persist keys in a local private env file used by automation:

```bash
mkdir -p "$HOME/.config/newproject"
cat > "$HOME/.config/newproject/supabase.env" <<'EOF'
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
SUPABASE_SCHEMA=public
EOF
chmod 600 "$HOME/.config/newproject/supabase.env"
```

## 3) Dry-run sync (safe test)

```bash
python3 "/Users/ray/Documents/Rayviews/tools/supabase_sync_ops.py" --dry-run
```

## 4) Real sync

```bash
python3 "/Users/ray/Documents/Rayviews/tools/supabase_sync_ops.py"
```

## 5) Verify in Supabase SQL Editor

```sql
select count(*) from ops_policy;
select count(*) from ops_mission_proposals;
select count(*) from ops_missions;
select count(*) from ops_mission_steps;
select count(*) from ops_agent_events;

-- RLS should be enabled on all ops tables:
select tablename, rowsecurity
from pg_tables
where schemaname = 'public'
  and tablename like 'ops_%'
order by tablename;
```

## 6) Keep it updated automatically (recommended)

Install LaunchAgent (macOS) every 10 minutes:

```bash
"/Users/ray/Documents/Rayviews/tools/install_supabase_sync_launchagent.sh" \
  --env-file "$HOME/.config/newproject/supabase.env" \
  --interval-seconds 600
```

Manual run using persisted env file:

```bash
"/Users/ray/Documents/Rayviews/tools/supabase_sync_runner.sh" --dry-run
"/Users/ray/Documents/Rayviews/tools/supabase_sync_runner.sh"
```

## Notes

- Use `SERVICE_ROLE_KEY` only on your machine/VPS, never client-side.
- If keys rotate, update env and rerun sync.
- This sync is additive/idempotent by primary keys and `event_hash`.
- If you already had ops files in `/Users/ray/Documents/Rayviews/ops`, the installer seeds them into `~/.config/newproject/ops` on first run.
