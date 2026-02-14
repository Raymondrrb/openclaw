-- 010 — Claim-next worker queue + force-unlock RPC + heartbeat hardening.
-- Run in Supabase SQL Editor after 009_worker_lease_lock.sql.
--
-- RPCs: rpc_claim_next_run, rpc_force_unlock_run, cas_heartbeat_run, rpc_release_run.
-- All RPCs: SECURITY DEFINER, SET search_path = public, lease clamp 1-30, worker_id validation.
-- Enterprise hardenings: pgcrypto, REVOKE/GRANT, status guard, null-safe, forensic snapshot.

-- ==========================================================================
-- 0. Prerequisites
-- ==========================================================================

-- gen_random_uuid() requires pgcrypto
create extension if not exists pgcrypto;

-- ==========================================================================
-- 1. Indexes for claim-next, lock audit, and worker health
-- ==========================================================================

-- Partial index for claim_next: only claimable statuses
create index if not exists idx_runs_claim_next
    on public.pipeline_runs (status, created_at asc)
    where status in ('running', 'in_progress', 'approved');

-- Partial index for lock audit: runs with active locks
create index if not exists idx_runs_lock_audit
    on public.pipeline_runs (status, lock_expires_at)
    where status in ('running', 'in_progress', 'approved', 'waiting_approval');

-- Worker health dashboard: quickly find panicked or stale workers
create index if not exists idx_runs_worker_health
    on public.pipeline_runs (worker_state, last_heartbeat_at desc)
    where worker_state in ('active', 'panic', 'waiting');

-- ==========================================================================
-- 2. rpc_claim_next_run — atomic "take the next eligible run" with recovery
--
-- Two-phase priority:
--   Phase 1 (recovery): If this worker already owns an active run with
--     a valid lease, reclaim it. Prevents "losing your run" on restart.
--   Phase 2 (fresh claim): Pick the next free/expired run via
--     FOR UPDATE OF r SKIP LOCKED. No collision between workers.
--
-- Token + locked_at stability: only rotated when ownership changes.
-- This prevents checkpoint invalidation on reclaim.
-- ==========================================================================

create or replace function public.rpc_claim_next_run(
    p_worker_id      text,
    p_lock_token     text,
    p_lease_minutes  int default 10,
    p_task_type      text default null
) returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_run_id uuid;
    v_now    timestamptz := now();
    v_lease  int := greatest(1, least(p_lease_minutes, 30));
begin
    -- Validate worker_id (min 3 chars after trim)
    if length(trim(p_worker_id)) < 3 then
        raise exception 'worker_id must be at least 3 characters, got "%"', trim(p_worker_id);
    end if;

    -- Phase 1: Recovery — reclaim our own active run (if any).
    -- Worker restarted without checkpoint → get your last run back.
    -- FOR UPDATE OF r (no SKIP LOCKED): it's our own run, we want it.
    select r.id into v_run_id
    from public.pipeline_runs r
    where r.worker_id = p_worker_id
      and r.lock_expires_at >= v_now
      and r.status in ('running', 'in_progress', 'approved', 'waiting_approval')
    order by r.locked_at desc nulls last
    limit 1
    for update of r;

    if v_run_id is not null then
        -- Reclaim: extend lease, keep token + locked_at (stable).
        -- worker_id set explicitly for consistency (idempotent here).
        update public.pipeline_runs
        set worker_id            = p_worker_id,
            lock_expires_at      = v_now + make_interval(mins => v_lease),
            last_heartbeat_at    = v_now,
            worker_state         = case
                when status = 'waiting_approval' then 'waiting'
                else 'active'
            end,
            worker_last_error    = ''
        where id = v_run_id;
        return v_run_id;
    end if;

    -- Phase 2: Fresh claim — next free/expired run.
    -- FOR UPDATE OF r SKIP LOCKED: atomic, no collision between workers.
    select r.id into v_run_id
    from public.pipeline_runs r
    where r.status in ('running', 'in_progress', 'approved')
      and (
          r.worker_id is null
          or r.worker_id = ''
          or r.lock_expires_at is null
          or r.lock_expires_at < v_now
      )
      and (p_task_type is null or r.task_type = p_task_type)
    order by
        case when r.status = 'approved' then 1 else 2 end,
        r.created_at asc
    limit 1
    for update of r skip locked;

    if v_run_id is null then
        return null;  -- No eligible runs
    end if;

    -- Fresh claim: new token + locked_at (ownership change)
    update public.pipeline_runs
    set worker_id            = p_worker_id,
        locked_at            = v_now,
        lock_expires_at      = v_now + make_interval(mins => v_lease),
        lock_token           = p_lock_token,
        worker_state         = 'active',
        last_heartbeat_at    = v_now,
        worker_last_error    = ''
    where id = v_run_id;

    return v_run_id;
end;
$$;

-- ==========================================================================
-- 3. rpc_force_unlock_run — operator unlock with full forensic snapshot
--
-- 4 micro-hardenings applied:
--   H1. Run not found → return false (no silent NULL passthrough)
--   H2. lock_expires_at IS NULL handled correctly (NULL < now() = NULL)
--   H3. Full prev snapshot: worker, token, locked_at, lock_expires_at, status
--   H4. Status guard: non-force only unlocks active states
--
-- Clears lock fields + sets worker_state='idle' + clears worker_last_error.
-- Does NOT change run status.
-- ==========================================================================

create or replace function public.rpc_force_unlock_run(
    p_run_id       uuid,
    p_operator_id  text,
    p_reason       text,
    p_force        boolean default false
) returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
    v_rows int;
    v_prev record;
begin
    -- Validate operator_id
    if length(trim(p_operator_id)) < 3 then
        raise exception 'operator_id must be at least 3 characters, got "%"', trim(p_operator_id);
    end if;

    -- H1: Capture full prev snapshot — if run doesn't exist, return false
    select worker_id, lock_token, locked_at, lock_expires_at, status, worker_state
    into v_prev
    from public.pipeline_runs
    where id = p_run_id;

    if not found then
        return false;  -- Run does not exist
    end if;

    -- H4: Status guard — non-force only unlocks active/gated states.
    -- Prevents accidental "unlock" on terminal runs (done/failed/aborted).
    if not p_force and v_prev.status not in (
        'running', 'in_progress', 'approved', 'waiting_approval'
    ) then
        return false;  -- Cannot unlock terminal state without force
    end if;

    -- Clear lock fields + reset worker health state.
    -- H2: lock_expires_at IS NULL is explicitly handled (NULL < now() = NULL → must check IS NULL).
    -- Force: always. Non-force: only if lease expired or NULL.
    update public.pipeline_runs
    set worker_id          = '',
        locked_at          = null,
        lock_expires_at    = null,
        lock_token         = '',
        worker_state       = 'idle',
        worker_last_error  = left('manual_unlock: ' || coalesce(p_reason, ''), 500)
    where id = p_run_id
      and (
          p_force = true
          or lock_expires_at is null
          or lock_expires_at < now()
      );

    get diagnostics v_rows = row_count;

    if v_rows > 0 then
        -- H3: Write forensic event with full prev snapshot
        insert into public.run_events (run_id, action_id, event_type, payload, created_at)
        values (
            p_run_id,
            gen_random_uuid()::text,
            'manual_unlock',
            jsonb_build_object(
                'operator_id',          p_operator_id,
                'reason',               p_reason,
                'force',                p_force,
                'prev_worker_id',       coalesce(v_prev.worker_id, ''),
                'prev_lock_token',      coalesce(v_prev.lock_token, ''),
                'prev_locked_at',       v_prev.locked_at,
                'prev_lock_expires_at', v_prev.lock_expires_at,
                'prev_status',          coalesce(v_prev.status, ''),
                'prev_worker_state',    coalesce(v_prev.worker_state, ''),
                'ts',                   now()
            ),
            now()
        );
        return true;
    end if;

    return false;
end;
$$;

-- ==========================================================================
-- 4. Worker health columns — observable state for dashboard
-- ==========================================================================

alter table public.pipeline_runs
    add column if not exists last_heartbeat_at timestamptz;
alter table public.pipeline_runs
    add column if not exists worker_state text not null default 'idle';
    -- values: 'idle' | 'active' | 'waiting' | 'panic'
alter table public.pipeline_runs
    add column if not exists worker_last_error text not null default '';
alter table public.pipeline_runs
    add column if not exists last_heartbeat_latency_ms int;

-- ==========================================================================
-- 5. Updated heartbeat RPC — records last_heartbeat_at + latency_ms
--
-- Sets worker_state based on current run status:
--   - waiting_approval → 'waiting' (worker is alive but paused)
--   - active states → 'active'
--
-- p_latency_ms: optional round-trip latency measured by the worker.
-- Stored for dashboard alerting (e.g., >5000ms = network degraded).
-- ==========================================================================

create or replace function public.cas_heartbeat_run(
    p_run_id         uuid,
    p_worker_id      text,
    p_lock_token     text,
    p_lease_minutes  int default 10,
    p_latency_ms     int default null
) returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
    rows_affected int;
    v_status text;
begin
    -- Clamp lease to 1-30 minutes
    p_lease_minutes := greatest(1, least(p_lease_minutes, 30));

    -- Get current status to determine worker_state
    select status into v_status
    from public.pipeline_runs
    where id = p_run_id
      and worker_id = p_worker_id
      and lock_token = p_lock_token;

    if v_status is null then
        return false;  -- Token/worker mismatch or run not found
    end if;

    -- Only renew for active or waiting states
    if v_status not in ('running', 'in_progress', 'approved', 'waiting_approval') then
        return false;  -- Terminal state — no heartbeat
    end if;

    -- Renew lease + update telemetry
    update public.pipeline_runs
    set lock_expires_at            = now() + make_interval(mins => p_lease_minutes),
        last_heartbeat_at          = now(),
        last_heartbeat_latency_ms  = coalesce(p_latency_ms, last_heartbeat_latency_ms),
        worker_state               = case
            when v_status = 'waiting_approval' then 'waiting'
            else 'active'
        end
    where id = p_run_id
      and worker_id = p_worker_id
      and lock_token = p_lock_token;

    get diagnostics rows_affected = row_count;
    return rows_affected > 0;
end;
$$;

-- ==========================================================================
-- 6. rpc_release_run — clean lock release on run completion
--
-- Worker calls this when a run finishes (done/failed/aborted).
-- Only the current holder (matching worker_id + lock_token) can release.
-- Sets worker_state='idle' and clears lock fields.
-- Does NOT change run status — that's the caller's responsibility.
-- ==========================================================================

create or replace function public.rpc_release_run(
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
    set worker_id                  = '',
        locked_at                  = null,
        lock_expires_at            = null,
        lock_token                 = '',
        worker_state               = 'idle',
        last_heartbeat_latency_ms  = null,
        worker_last_error          = ''
    where id = p_run_id
      and worker_id = p_worker_id
      and lock_token = p_lock_token;

    get diagnostics rows_affected = row_count;
    return rows_affected > 0;
end;
$$;

-- ==========================================================================
-- 7. Access control — RPCs only callable via service_role (backend)
--
-- RLS denies anon/authenticated on tables. This also locks the RPCs
-- so nobody can call them directly from the client.
-- ==========================================================================

revoke execute on function public.rpc_claim_next_run(text, text, int, text) from public;
revoke execute on function public.rpc_force_unlock_run(uuid, text, text, boolean) from public;
revoke execute on function public.cas_heartbeat_run(uuid, text, text, int, int) from public;
revoke execute on function public.rpc_release_run(uuid, text, text) from public;

grant execute on function public.rpc_claim_next_run(text, text, int, text) to service_role;
grant execute on function public.rpc_force_unlock_run(uuid, text, text, boolean) to service_role;
grant execute on function public.cas_heartbeat_run(uuid, text, text, int, int) to service_role;
grant execute on function public.rpc_release_run(uuid, text, text) to service_role;
