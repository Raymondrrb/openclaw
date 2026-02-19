-- Distributed step lock table for pipeline run_id + step_name.
-- TTL-based lock recovery: stale locks are reclaimed when expires_at < now().

create table if not exists public.ops_step_locks (
  run_id text not null,
  step_name text not null,
  owner text not null,
  lock_token text not null,
  locked_at timestamptz not null default now(),
  heartbeat_at timestamptz not null default now(),
  expires_at timestamptz not null,
  primary key (run_id, step_name),
  constraint ops_step_locks_expires_after_locked
    check (expires_at >= locked_at)
);

create index if not exists idx_ops_step_locks_expires_at
  on public.ops_step_locks (expires_at);

alter table if exists public.ops_step_locks enable row level security;
revoke all on table public.ops_step_locks from anon, authenticated;
grant select, insert, update, delete on table public.ops_step_locks to service_role;
