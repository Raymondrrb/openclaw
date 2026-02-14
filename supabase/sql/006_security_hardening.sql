-- 006_security_hardening.sql
-- Supabase Security Advisor remediation: RLS + GRANTs hardening.
-- Run in Supabase SQL Editor.
--
-- Fixes:
--   1. CRITICAL: Enable RLS on ops_* tables (created outside migrations, no RLS)
--   2. Revoke unused authenticated SELECT grants on pipeline tables
--      (dashboard uses service_role via server components, not authenticated)
--   3. Revoke anon access everywhere (never used)
--   4. Advisory: pg_temp search path (Supabase-internal, noted below)
--
-- Principle: default-deny. Only service_role has access.

BEGIN;

-- =========================================================================
-- 1. ops_* tables — Enable RLS + service_role-only policies
--    These tables were created via dashboard and lack RLS entirely.
-- =========================================================================

-- ops_agent_events
ALTER TABLE IF EXISTS public.ops_agent_events ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY "Service role full access" ON public.ops_agent_events
        FOR ALL USING (auth.role() = 'service_role')
        WITH CHECK (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
REVOKE ALL ON public.ops_agent_events FROM anon;
REVOKE ALL ON public.ops_agent_events FROM authenticated;
GRANT ALL  ON public.ops_agent_events TO service_role;

-- ops_mission_proposals
ALTER TABLE IF EXISTS public.ops_mission_proposals ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY "Service role full access" ON public.ops_mission_proposals
        FOR ALL USING (auth.role() = 'service_role')
        WITH CHECK (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
REVOKE ALL ON public.ops_mission_proposals FROM anon;
REVOKE ALL ON public.ops_mission_proposals FROM authenticated;
GRANT ALL  ON public.ops_mission_proposals TO service_role;

-- ops_mission_steps
ALTER TABLE IF EXISTS public.ops_mission_steps ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY "Service role full access" ON public.ops_mission_steps
        FOR ALL USING (auth.role() = 'service_role')
        WITH CHECK (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
REVOKE ALL ON public.ops_mission_steps FROM anon;
REVOKE ALL ON public.ops_mission_steps FROM authenticated;
GRANT ALL  ON public.ops_mission_steps TO service_role;

-- ops_missions
ALTER TABLE IF EXISTS public.ops_missions ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY "Service role full access" ON public.ops_missions
        FOR ALL USING (auth.role() = 'service_role')
        WITH CHECK (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
REVOKE ALL ON public.ops_missions FROM anon;
REVOKE ALL ON public.ops_missions FROM authenticated;
GRANT ALL  ON public.ops_missions TO service_role;

-- ops_policy
ALTER TABLE IF EXISTS public.ops_policy ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY "Service role full access" ON public.ops_policy
        FOR ALL USING (auth.role() = 'service_role')
        WITH CHECK (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
REVOKE ALL ON public.ops_policy FROM anon;
REVOKE ALL ON public.ops_policy FROM authenticated;
GRANT ALL  ON public.ops_policy TO service_role;

-- =========================================================================
-- 2. Pipeline tables — Revoke authenticated SELECT (unused, dashboard
--    uses service_role). This eliminates the "Auth RLS Initialization Plan"
--    warnings since authenticated will have no grants at all.
-- =========================================================================

REVOKE SELECT ON public.pipeline_runs     FROM authenticated;
REVOKE SELECT ON public.niches            FROM authenticated;
REVOKE SELECT ON public.research_sources  FROM authenticated;
REVOKE SELECT ON public.shortlist_items   FROM authenticated;
REVOKE SELECT ON public.amazon_products   FROM authenticated;
REVOKE SELECT ON public.top5             FROM authenticated;
REVOKE SELECT ON public.scripts          FROM authenticated;
REVOKE SELECT ON public.assets           FROM authenticated;
REVOKE SELECT ON public.tts_audio        FROM authenticated;
REVOKE SELECT ON public.agent_events     FROM authenticated;
REVOKE SELECT ON public.lessons          FROM authenticated;
REVOKE SELECT ON public.channel_memory   FROM authenticated;
REVOKE SELECT ON public.video_metrics    FROM authenticated;

-- Also revoke from anon (should already be revoked, belt-and-suspenders)
REVOKE ALL ON public.pipeline_runs     FROM anon;
REVOKE ALL ON public.niches            FROM anon;
REVOKE ALL ON public.research_sources  FROM anon;
REVOKE ALL ON public.shortlist_items   FROM anon;
REVOKE ALL ON public.amazon_products   FROM anon;
REVOKE ALL ON public.top5             FROM anon;
REVOKE ALL ON public.scripts          FROM anon;
REVOKE ALL ON public.assets           FROM anon;
REVOKE ALL ON public.tts_audio        FROM anon;
REVOKE ALL ON public.agent_events     FROM anon;
REVOKE ALL ON public.lessons          FROM anon;
REVOKE ALL ON public.channel_memory   FROM anon;
REVOKE ALL ON public.video_metrics    FROM anon;

-- dzine_generations (from 004_dzine_generations.sql)
REVOKE ALL ON public.dzine_generations FROM anon;
REVOKE ALL ON public.dzine_generations FROM authenticated;

-- =========================================================================
-- 3. Fix pg_temp function search path advisory
--    pg_temp_44.count_estimate is a Supabase-internal temp function.
--    We can't modify it directly, but we can drop it if it lingers
--    from a previous session. If it doesn't exist, this is a no-op.
-- =========================================================================

-- Drop the temp function if it exists (safe — it's session-scoped anyway)
DROP FUNCTION IF EXISTS pg_temp_44.count_estimate(text);

-- =========================================================================
-- 4. Verify: after running, check these in Security Advisor
-- =========================================================================

-- Verification queries (run manually after migration):
--
-- Check RLS is enabled on all public tables:
--   SELECT schemaname, tablename, rowsecurity
--   FROM pg_tables
--   WHERE schemaname = 'public'
--   ORDER BY tablename;
--
-- Check policies exist:
--   SELECT schemaname, tablename, policyname, permissive, roles, cmd
--   FROM pg_policies
--   WHERE schemaname = 'public'
--   ORDER BY tablename;
--
-- Check grants (should only show service_role):
--   SELECT grantee, table_name, privilege_type
--   FROM information_schema.table_privileges
--   WHERE table_schema = 'public'
--     AND grantee IN ('anon', 'authenticated')
--   ORDER BY table_name, grantee;

COMMIT;
