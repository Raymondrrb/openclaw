-- Ops core schema for Supabase (Postgres)
-- Run this in Supabase SQL Editor before using sync scripts.

create table if not exists ops_policy (
  key text primary key,
  value jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists ops_mission_proposals (
  id text primary key,
  title text not null,
  category text,
  status text not null check (status in ('pending', 'approved', 'rejected')),
  reason text,
  created_at timestamptz not null default now()
);

create table if not exists ops_missions (
  id text primary key,
  proposal_id text references ops_mission_proposals(id) on delete set null,
  title text not null,
  status text not null check (status in ('queued', 'approved', 'running', 'succeeded', 'failed')),
  created_at timestamptz not null default now()
);

create table if not exists ops_mission_steps (
  id text primary key,
  mission_id text not null references ops_missions(id) on delete cascade,
  kind text not null,
  status text not null check (status in ('queued', 'running', 'succeeded', 'failed')),
  reserved_at timestamptz,
  error text
);

create index if not exists idx_ops_mission_steps_mission_id on ops_mission_steps(mission_id);
create index if not exists idx_ops_mission_steps_status on ops_mission_steps(status);

create table if not exists ops_agent_events (
  id bigserial primary key,
  event_hash text unique not null,
  ts timestamptz not null,
  type text not null,
  message text not null,
  data jsonb
);

create index if not exists idx_ops_agent_events_ts on ops_agent_events(ts desc);
create index if not exists idx_ops_agent_events_type on ops_agent_events(type);

