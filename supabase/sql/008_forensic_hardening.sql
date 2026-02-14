-- 008_forensic_hardening.sql — production hardening for forensic infrastructure.
-- Run in Supabase SQL Editor after 007_run_manager_schema.sql.
--
-- Idempotent: safe to re-run. All operations check before acting.
--
-- What this migration does:
--   1. UNIQUE(run_id, evidence_id) on run_evidence  (no duplicate evidence per run)
--   2. FK evidence_id → ON DELETE RESTRICT           (preserve forensic trail)
--   3. RLS WITH CHECK(false) on all operational tables
--   4. Triggers via pg_trigger check                 (no error swallowing)
--   5. Partial index for Tier 4/5 conflict queries
--   6. Housekeeping-safe deletion template

-- ==========================================================================
-- 0. Ensure set_updated_at() exists (dependency for triggers)
-- ==========================================================================

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

-- ==========================================================================
-- 1. UNIQUE(run_id, evidence_id) on run_evidence
-- ==========================================================================
-- Prevents: same evidence attached twice to same run (retry, concurrency, bug).
-- Impact: inflated MPC scores, misleading rayvault stats.

create unique index if not exists idx_run_evidence_unique
    on public.run_evidence (run_id, evidence_id);

-- ==========================================================================
-- 2. FK run_evidence.evidence_id → ON DELETE RESTRICT
-- ==========================================================================
-- Prevents: housekeeping job deleting evidence that sustained a published video.
-- Impact: if a viewer disputes a claim, you can prove what evidence existed.
--
-- Dynamic FK discovery: does NOT assume the constraint name.

do $$
declare
    fk_name text;
begin
    -- Find existing FK from run_evidence.evidence_id → evidence_items.id
    select c.conname into fk_name
    from pg_constraint c
    join pg_attribute a on a.attrelid = c.conrelid
                       and a.attnum = any(c.conkey)
    where c.conrelid  = 'public.run_evidence'::regclass
      and c.confrelid = 'public.evidence_items'::regclass
      and c.contype   = 'f'
      and a.attname   = 'evidence_id';

    -- Drop old FK if it exists and isn't already our target name
    if fk_name is not null and fk_name != 'run_evidence_evidence_id_restrict' then
        execute format('alter table public.run_evidence drop constraint %I', fk_name);
    end if;

    -- Create deterministic FK with RESTRICT (if not already present)
    if not exists (
        select 1 from pg_constraint
        where conname = 'run_evidence_evidence_id_restrict'
          and conrelid = 'public.run_evidence'::regclass
    ) then
        alter table public.run_evidence
            add constraint run_evidence_evidence_id_restrict
            foreign key (evidence_id)
            references public.evidence_items(id)
            on delete restrict;
    end if;
end
$$;

-- ==========================================================================
-- 3. RLS: deny anon + authenticated with USING(false) + WITH CHECK(false)
-- ==========================================================================
-- Backend uses service_role key which bypasses RLS entirely.
-- These policies block any anon/authenticated path (edge functions, PostgREST, etc).
--
-- NOTE: WITH CHECK(false) explicitly blocks INSERT/UPDATE via the check path.
-- Without it, some edge cases may allow writes depending on policy evaluation.

-- 3a. run_events
alter table public.run_events enable row level security;
drop policy if exists "deny anon run_events" on public.run_events;
create policy "deny anon run_events" on public.run_events
    for all to anon using (false) with check (false);
drop policy if exists "deny authenticated run_events" on public.run_events;
create policy "deny authenticated run_events" on public.run_events
    for all to authenticated using (false) with check (false);

-- 3b. evidence_items
alter table public.evidence_items enable row level security;
drop policy if exists "deny anon evidence_items" on public.evidence_items;
create policy "deny anon evidence_items" on public.evidence_items
    for all to anon using (false) with check (false);
drop policy if exists "deny authenticated evidence_items" on public.evidence_items;
create policy "deny authenticated evidence_items" on public.evidence_items
    for all to authenticated using (false) with check (false);

-- 3c. run_evidence
alter table public.run_evidence enable row level security;
drop policy if exists "deny anon run_evidence" on public.run_evidence;
create policy "deny anon run_evidence" on public.run_evidence
    for all to anon using (false) with check (false);
drop policy if exists "deny authenticated run_evidence" on public.run_evidence;
create policy "deny authenticated run_evidence" on public.run_evidence
    for all to authenticated using (false) with check (false);

-- 3d. product_fingerprints
alter table public.product_fingerprints enable row level security;
drop policy if exists "deny anon product_fingerprints" on public.product_fingerprints;
create policy "deny anon product_fingerprints" on public.product_fingerprints
    for all to anon using (false) with check (false);
drop policy if exists "deny authenticated product_fingerprints" on public.product_fingerprints;
create policy "deny authenticated product_fingerprints" on public.product_fingerprints
    for all to authenticated using (false) with check (false);

-- ==========================================================================
-- 4. Triggers via pg_trigger (no error swallowing)
-- ==========================================================================
-- Pattern: check pg_trigger catalog, create only if missing.
-- Avoids DO/EXCEPTION WHEN OTHERS which hides real errors.

-- 4a. pipeline_runs.updated_at
do $$
begin
    if not exists (
        select 1 from pg_trigger
        where tgname  = 'trg_pipeline_runs_updated_at'
          and tgrelid = 'public.pipeline_runs'::regclass
    ) then
        create trigger trg_pipeline_runs_updated_at
            before update on public.pipeline_runs
            for each row execute function public.set_updated_at();
    end if;
end
$$;

-- 4b. evidence_items.updated_at
do $$
begin
    if not exists (
        select 1 from pg_trigger
        where tgname  = 'trg_evidence_items_updated_at'
          and tgrelid = 'public.evidence_items'::regclass
    ) then
        create trigger trg_evidence_items_updated_at
            before update on public.evidence_items
            for each row execute function public.set_updated_at();
    end if;
end
$$;

-- 4c. product_fingerprints.updated_at
do $$
begin
    if not exists (
        select 1 from pg_trigger
        where tgname  = 'trg_product_fingerprints_updated_at'
          and tgrelid = 'public.product_fingerprints'::regclass
    ) then
        create trigger trg_product_fingerprints_updated_at
            before update on public.product_fingerprints
            for each row execute function public.set_updated_at();
    end if;
end
$$;

-- ==========================================================================
-- 5. Performance indexes
-- ==========================================================================

-- 5a. Partial index: fast Tier 4/5 conflict detection
-- Used by: circuit_breaker.detect_conflicts(), rayvault_stats reputation risk
create index if not exists idx_evidence_tier4plus
    on public.evidence_items (normalized_id, claim_type, fetched_at desc)
    where trust_tier >= 4;

-- 5b. Expiration housekeeping
create index if not exists idx_evidence_expires_at
    on public.evidence_items (expires_at)
    where expires_at is not null;

-- ==========================================================================
-- 6. Housekeeping: safe evidence deletion template
-- ==========================================================================
-- DO NOT run blindly. This deletes expired evidence that was NEVER used in any run.
-- Evidence referenced by run_evidence is protected by ON DELETE RESTRICT.
--
-- Usage: run manually or via scheduled job. Always test with SELECT first.
--
-- -- Preview what would be deleted:
-- SELECT e.id, e.asin, e.claim_type, e.expires_at
-- FROM public.evidence_items e
-- WHERE e.expires_at < now()
--   AND NOT EXISTS (
--       SELECT 1 FROM public.run_evidence re WHERE re.evidence_id = e.id
--   );
--
-- -- Actually delete (only unreferenced expired evidence):
-- DELETE FROM public.evidence_items e
-- WHERE e.expires_at < now()
--   AND NOT EXISTS (
--       SELECT 1 FROM public.run_evidence re WHERE re.evidence_id = e.id
--   );
--
-- Alternative: soft-archive instead of deleting.
-- UPDATE evidence_items SET source_type = 'archived' WHERE ...

-- ==========================================================================
-- Done. Verify with: SELECT * FROM rayvault_doctor checks (see tools/rayvault_doctor.py)
-- ==========================================================================
