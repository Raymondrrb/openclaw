# 006 Security Hardening — Checklist

## What This Migration Does

1. **Enables RLS on 5 ops_* tables** (ops_agent_events, ops_mission_proposals, ops_mission_steps, ops_missions, ops_policy) — these had NO RLS
2. **Creates service_role-only policies** on ops_* tables — deny all to anon/authenticated
3. **Revokes authenticated SELECT** from all 13 pipeline tables + dzine_generations — was unused (dashboard uses service_role via server components)
4. **Revokes anon access** everywhere (belt-and-suspenders)
5. **Drops pg_temp function** if lingering from a previous session

## What Might Break

| Component | Risk | Why It's Safe |
|-----------|------|---------------|
| Python pipeline (`supabase_client.py`) | None | Uses service_role key exclusively |
| Web dashboard (`web/lib/queries.ts`) | None | Server components use service_role via `web/lib/supabase/server.ts` |
| Browser client (`web/lib/supabase/client.ts`) | None | Not used anywhere — prepared for future only |
| Supabase PostgREST API | None | All API calls use service_role key header |
| Storage buckets | None | Storage policies are separate from table RLS |

## How To Test

### 1. Run the migration
```sql
-- In Supabase SQL Editor: paste contents of 006_security_hardening.sql
```

### 2. Verify RLS is enabled on all tables
```sql
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
-- Expected: ALL rows show rowsecurity = true
```

### 3. Verify no anon/authenticated grants remain
```sql
SELECT grantee, table_name, privilege_type
FROM information_schema.table_privileges
WHERE table_schema = 'public'
  AND grantee IN ('anon', 'authenticated')
ORDER BY table_name, grantee;
-- Expected: empty result set (0 rows)
```

### 4. Verify service_role still works
```bash
# Python: should succeed
python3 -c "
from tools.lib.supabase_client import query
rows = query('pipeline_runs', select='id', limit=1)
print('OK:', rows)
"

# Web: should succeed
cd web && npm run build
# Then test /api/health endpoint
```

### 5. Verify anon cannot read ops_* tables
```sql
-- In SQL Editor, switch to anon role:
SET ROLE anon;
SELECT * FROM public.ops_missions LIMIT 1;
-- Expected: ERROR: permission denied / 0 rows (RLS blocks)
RESET ROLE;
```

### 6. Re-check Security Advisor
- Navigate to Supabase Dashboard > Security Advisor
- "RLS Disabled in Public" alerts for ops_* should be gone
- "Auth RLS Initialization Plan" warnings should be resolved
- "Function Search Path Mutable" may persist (Supabase-internal)

## Notes

- The `pg_temp_44.count_estimate` function is session-scoped and Supabase-internal. The `DROP FUNCTION` may not resolve the advisory permanently. If the warning persists, it's a known Supabase issue — not actionable from our side.
- If we ever need authenticated access in the future (e.g., for a user-facing dashboard), we'd add specific SELECT policies with user_id filtering, not broad GRANT SELECT.
