-- Worker lease lock: prevents 2+ workers from claiming the same run.
-- Run in Supabase SQL Editor after 008_forensic_hardening.sql.
--
-- Pattern: lease with expiration (not a permanent lock).
--   - Worker claims run with CAS (only if lock expired or null).
--   - Worker renews lease every 2-3 min (heartbeat).
--   - If worker crashes, lease expires → other worker can reclaim.
--   - lock_token (uuid) prevents accidental unlock by wrong worker.
--
-- SRE hardenings:
--   - SET search_path = public in all RPCs (prevents schema hijack)
--   - Lease clamp 1-30 min (prevents client bugs from setting absurd leases)
--   - worker_id validation (min 3 chars after trim)
--   - Token renewal: fresh claim → new token, reclaim by same worker → keep existing

-- ==========================================================================
-- 1. Add lease columns to pipeline_runs
-- ==========================================================================

alter table public.pipeline_runs
    add column if not exists worker_id text not null default '';
alter table public.pipeline_runs
    add column if not exists locked_at timestamptz;
alter table public.pipeline_runs
    add column if not exists lock_expires_at timestamptz;
alter table public.pipeline_runs
    add column if not exists lock_token text not null default '';

-- Primary index for worker polling: "give me the next claimable run"
-- Covers: status IN ('running','approved') AND (lock_expires_at IS NULL OR < now())
create index if not exists idx_runs_locking
    on public.pipeline_runs (status, lock_expires_at, created_at desc);

-- Index for expired-lock cleanup queries and force_release
create index if not exists idx_runs_lock_expiry
    on public.pipeline_runs (lock_expires_at)
    where lock_expires_at is not null;

-- Index for unclaimed runs (worker_id is empty, status is claimable)
create index if not exists idx_runs_unclaimed
    on public.pipeline_runs (status, created_at desc)
    where worker_id = '';

-- ==========================================================================
-- 2. CAS claim function — atomic "take this run if nobody else has it"
-- ==========================================================================

create or replace function public.cas_claim_run(
    p_run_id         uuid,
    p_worker_id      text,
    p_lock_token     text,
    p_lease_minutes  int default 10
) returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
    rows_affected int;
begin
    -- Validate worker_id (min 3 chars after trim)
    if length(trim(p_worker_id)) < 3 then
        raise exception 'worker_id must be at least 3 characters, got "%"', trim(p_worker_id);
    end if;

    -- Clamp lease to 1-30 minutes (prevent client bugs)
    p_lease_minutes := greatest(1, least(p_lease_minutes, 30));

    -- Claim if: lock is free/expired, OR same worker reclaiming (idempotent).
    -- Token + locked_at logic: ownership change → new values.
    --                          reclaim by same worker → keep existing (audit trail stays honest).
    update public.pipeline_runs
    set worker_id       = p_worker_id,
        locked_at       = case
            when worker_id = p_worker_id and lock_expires_at >= now()
                then locked_at                                -- reclaim: keep original timestamp
            else now()                                        -- fresh claim: new timestamp
        end,
        lock_expires_at = now() + make_interval(mins => p_lease_minutes),
        lock_token      = case
            when worker_id = p_worker_id and lock_expires_at >= now()
                then lock_token                               -- reclaim: keep existing token
            else p_lock_token                                 -- fresh claim: new token
        end
    where id = p_run_id
      and status in ('running', 'in_progress', 'approved')
      and (
          -- Lock free or expired
          worker_id = '' or lock_expires_at is null or lock_expires_at < now()
          -- OR same worker reclaiming
          or worker_id = p_worker_id
      );

    get diagnostics rows_affected = row_count;
    return rows_affected > 0;
end;
$$;

-- ==========================================================================
-- 3. Heartbeat function — renew lease (only by correct worker + token)
-- ==========================================================================

create or replace function public.cas_heartbeat_run(
    p_run_id         uuid,
    p_worker_id      text,
    p_lock_token     text,
    p_lease_minutes  int default 10
) returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
    rows_affected int;
begin
    -- Clamp lease to 1-30 minutes
    p_lease_minutes := greatest(1, least(p_lease_minutes, 30));

    -- Renew lease. Includes waiting_approval so worker retains
    -- ownership during gate (prevents race with another worker).
    update public.pipeline_runs
    set lock_expires_at = now() + make_interval(mins => p_lease_minutes)
    where id = p_run_id
      and worker_id = p_worker_id
      and lock_token = p_lock_token
      and status in ('running', 'in_progress', 'approved', 'waiting_approval');

    get diagnostics rows_affected = row_count;
    return rows_affected > 0;
end;
$$;

-- ==========================================================================
-- 4. Release function — clear lock fields (terminal states or manual)
-- ==========================================================================

create or replace function public.cas_release_run(
    p_run_id         uuid,
    p_worker_id      text,
    p_lock_token     text
) returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
    rows_affected int;
begin
    update public.pipeline_runs
    set worker_id       = '',
        locked_at       = null,
        lock_expires_at = null,
        lock_token      = ''
    where id = p_run_id
      and worker_id = p_worker_id
      and lock_token = p_lock_token;

    get diagnostics rows_affected = row_count;
    return rows_affected > 0;
end;
$$;

-- ==========================================================================
-- 5. Force release (dashboard) — only works if lease already expired
-- ==========================================================================

create or replace function public.force_release_expired_run(
    p_run_id uuid
) returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
    rows_affected int;
begin
    update public.pipeline_runs
    set worker_id       = '',
        locked_at       = null,
        lock_expires_at = null,
        lock_token      = ''
    where id = p_run_id
      and lock_expires_at < now();

    get diagnostics rows_affected = row_count;
    return rows_affected > 0;
end;
$$;
