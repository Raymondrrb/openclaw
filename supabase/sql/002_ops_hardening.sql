-- Ops hardening for Supabase Data API usage.
-- Apply after 001_ops_core.sql
--
-- Why:
-- 1) Lock down anon/authenticated access in Data API
-- 2) Keep backend sync on service_role key only
-- 3) Add query indexes used by operational dashboards/sweeps

-- Enable RLS on all ops tables.
alter table if exists public.ops_policy enable row level security;
alter table if exists public.ops_mission_proposals enable row level security;
alter table if exists public.ops_missions enable row level security;
alter table if exists public.ops_mission_steps enable row level security;
alter table if exists public.ops_agent_events enable row level security;

-- No policies are added on purpose: anon/authenticated are denied by default.
-- service_role bypasses RLS and is used by backend sync tooling.

-- Explicit grants/revokes for API roles.
revoke all on table public.ops_policy from anon, authenticated;
revoke all on table public.ops_mission_proposals from anon, authenticated;
revoke all on table public.ops_missions from anon, authenticated;
revoke all on table public.ops_mission_steps from anon, authenticated;
revoke all on table public.ops_agent_events from anon, authenticated;

grant select, insert, update, delete on table public.ops_policy to service_role;
grant select, insert, update, delete on table public.ops_mission_proposals to service_role;
grant select, insert, update, delete on table public.ops_missions to service_role;
grant select, insert, update, delete on table public.ops_mission_steps to service_role;
grant select, insert, update, delete on table public.ops_agent_events to service_role;

-- Sequence used by ops_agent_events.id (bigserial).
grant usage, select, update on sequence public.ops_agent_events_id_seq to service_role;

-- Operational indexes.
create index if not exists idx_ops_mission_proposals_status_created_at
  on public.ops_mission_proposals(status, created_at desc);

create index if not exists idx_ops_missions_status_created_at
  on public.ops_missions(status, created_at desc);

create index if not exists idx_ops_mission_steps_status_reserved_at
  on public.ops_mission_steps(status, reserved_at);

create index if not exists idx_ops_agent_events_type_ts
  on public.ops_agent_events(type, ts desc);

