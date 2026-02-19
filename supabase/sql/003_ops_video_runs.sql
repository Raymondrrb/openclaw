-- Video pipeline state machine table (QUALITY FIRST gates).
-- Apply after 001_ops_core.sql and 002_ops_hardening.sql.

create table if not exists public.ops_video_runs (
  id bigserial primary key,
  run_slug text not null unique,
  theme text not null,
  category text not null,
  status text not null check (
    status in (
      'draft_ready_waiting_gate_1',
      'assets_ready_waiting_gate_2',
      'rendering',
      'uploading',
      'published',
      'failed'
    )
  ),
  gate1_approved boolean not null default false,
  gate2_approved boolean not null default false,
  gate1_reviewer text,
  gate2_reviewer text,
  gate1_notes text,
  gate2_notes text,
  artifacts jsonb not null default '{}'::jsonb,
  meta jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_ops_video_runs_status_updated_at
  on public.ops_video_runs(status, updated_at desc);

create index if not exists idx_ops_video_runs_gate_flags
  on public.ops_video_runs(gate1_approved, gate2_approved);

alter table if exists public.ops_video_runs enable row level security;

revoke all on table public.ops_video_runs from anon, authenticated;
grant select, insert, update, delete on table public.ops_video_runs to service_role;
grant usage, select, update on sequence public.ops_video_runs_id_seq to service_role;

