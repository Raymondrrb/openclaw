-- Claim-next worker queue + force-unlock RPC.
-- Run in Supabase SQL Editor after 009_worker_lease_lock.sql.
--
-- rpc_claim_next_run: atomic "give me the next eligible run" (FOR UPDATE SKIP LOCKED).
-- rpc_force_unlock_run: operator unlock with forensic trail in run_events.
--
-- All RPCs: SET search_path = public, lease clamp 1-30, worker_id validation.

-- ==========================================================================
-- 1. Indexes for claim-next and lock audit
-- ==========================================================================

-- Partial index for claim_next: only claimable statuses
create index if not exists idx_runs_claim_next
    on public.pipeline_runs (status, created_at asc)
    where status in ('running', 'in_progress', 'approved');

-- Partial index for lock audit: runs with active locks
create index if not exists idx_runs_lock_audit
    on public.pipeline_runs (status, lock_expires_at)
    where status in ('running', 'in_progress', 'approved', 'waiting_approval');

-- ==========================================================================
-- 2. rpc_claim_next_run — atomic "take the next eligible run"
--
-- Uses FOR UPDATE SKIP LOCKED so two workers calling simultaneously
-- each get a different run (no collision, no retry).
--
-- Priority: approved first (human already unblocked), then by created_at ASC.
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
    v_claimed boolean;
begin
    -- Validate worker_id (min 3 chars after trim)
    if length(trim(p_worker_id)) < 3 then
        raise exception 'worker_id must be at least 3 characters, got "%"', trim(p_worker_id);
    end if;

    -- Clamp lease to 1-30 minutes
    p_lease_minutes := greatest(1, least(p_lease_minutes, 30));

    -- Select next eligible run:
    --   1. Status is claimable (running, in_progress, approved)
    --   2. Lock is free, expired, or null (no active lock by another worker)
    --   3. Optional task_type filter
    --   4. Priority: approved > running/in_progress, then oldest first
    --   5. FOR UPDATE SKIP LOCKED: atomic, no collision between workers
    select id into v_run_id
    from public.pipeline_runs
    where status in ('running', 'in_progress', 'approved')
      and (
          worker_id is null
          or worker_id = ''
          or lock_expires_at is null
          or lock_expires_at < now()
      )
      and (p_task_type is null or task_type = p_task_type)
    order by
        case when status = 'approved' then 1 else 2 end,
        created_at asc
    limit 1
    for update skip locked;

    if v_run_id is null then
        return null;  -- No eligible runs
    end if;

    -- Claim it (inline, same transaction — no CAS race)
    update public.pipeline_runs
    set worker_id       = p_worker_id,
        locked_at       = now(),
        lock_expires_at = now() + make_interval(mins => p_lease_minutes),
        lock_token      = p_lock_token
    where id = v_run_id;

    return v_run_id;
end;
$$;

-- ==========================================================================
-- 3. rpc_force_unlock_run — operator unlock with forensic event
--
-- By default, only unlocks if the lease is already expired.
-- With p_force=true, unlocks regardless (emergency use).
-- Always writes a run_event for audit trail.
-- Does NOT change run status — only clears lock fields.
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
    v_old_worker text;
    v_old_token text;
begin
    -- Validate operator_id
    if length(trim(p_operator_id)) < 3 then
        raise exception 'operator_id must be at least 3 characters, got "%"', trim(p_operator_id);
    end if;

    -- Capture old lock info for the event payload
    select worker_id, lock_token
    into v_old_worker, v_old_token
    from public.pipeline_runs
    where id = p_run_id;

    -- Clear lock fields only (status unchanged)
    -- Default: only if expired. Force: always.
    update public.pipeline_runs
    set worker_id       = '',
        locked_at       = null,
        lock_expires_at = null,
        lock_token      = ''
    where id = p_run_id
      and (
          p_force = true
          or lock_expires_at is null
          or lock_expires_at < now()
      );

    get diagnostics v_rows = row_count;

    if v_rows > 0 then
        -- Write forensic event
        insert into public.run_events (run_id, action_id, event_type, payload, created_at)
        values (
            p_run_id,
            gen_random_uuid()::text,
            'manual_unlock',
            jsonb_build_object(
                'operator_id', p_operator_id,
                'reason', p_reason,
                'force', p_force,
                'prev_worker_id', coalesce(v_old_worker, ''),
                'prev_lock_token', coalesce(v_old_token, ''),
                'ts', now()
            ),
            now()
        );
        return true;
    end if;

    return false;
end;
$$;
