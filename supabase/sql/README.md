# Supabase SQL Files

Run these files in this exact order in Supabase SQL Editor:

1. `001_ops_core.sql`
2. `002_ops_hardening.sql`
3. `003_ops_video_runs.sql`
4. `004_ops_video_runs_locking.sql`
5. `005_ops_step_locks.sql`

## What each file does

- `001_ops_core.sql`: creates core ops tables used by local->Supabase sync.
- `002_ops_hardening.sql`: enables RLS, revokes anon/authenticated table access, grants service role access, and adds query indexes.
- `003_ops_video_runs.sql`: creates video run state machine table used by control-plane endpoints.
- `004_ops_video_runs_locking.sql`: adds CAS claim fields for ops video worker execution.
- `005_ops_step_locks.sql`: creates distributed per-step lock table with TTL/stale recovery support.

## Quick verify query

```sql
select tablename, rowsecurity
from pg_tables
where schemaname = 'public'
  and tablename like 'ops_%'
order by tablename;
```
