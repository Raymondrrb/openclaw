-- Worker claim-based locking and retry tracking for ops_video_runs.
-- Supports CAS (compare-and-swap) pattern for safe concurrent processing.

alter table public.ops_video_runs
  add column if not exists claimed_by text default null,
  add column if not exists claimed_at timestamptz default null,
  add column if not exists fail_count integer not null default 0;

create index if not exists idx_ops_video_runs_unclaimed
  on public.ops_video_runs(claimed_by) where claimed_by is null;
