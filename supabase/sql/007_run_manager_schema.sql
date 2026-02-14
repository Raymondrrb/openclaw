-- Run manager schema: state machine, approval gates, evidence, fingerprints.
-- Run in Supabase SQL Editor after 006_security_hardening.sql.
--
-- Security model: backend uses service_role key (bypasses RLS).
-- RLS denies anon + authenticated on ALL operational tables.
-- No frontend/public access to runs, events, evidence, or fingerprints.

create extension if not exists pgcrypto;

-- ==========================================================================
-- 0. Utility: auto-update updated_at trigger function
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
-- 1. Extend pipeline_runs — approval gate + context snapshots
-- ==========================================================================

-- Expand allowed statuses for state machine
alter table public.pipeline_runs
    drop constraint if exists pipeline_runs_status_check;
alter table public.pipeline_runs
    add constraint pipeline_runs_status_check
    check (status in (
        'pending', 'running', 'in_progress',
        'waiting_approval', 'approved',
        'complete', 'done', 'failed', 'aborted'
    ));

alter table public.pipeline_runs
    add column if not exists approval_nonce text not null default '';
alter table public.pipeline_runs
    add column if not exists context_snapshot jsonb not null default '{}';
alter table public.pipeline_runs
    add column if not exists policy_version text not null default '';
alter table public.pipeline_runs
    add column if not exists ranking_model text not null default '';

-- Executive logbook fields
alter table public.pipeline_runs
    add column if not exists tone_authority_level text not null default 'balanced';
alter table public.pipeline_runs
    add column if not exists variant_id text not null default '';
alter table public.pipeline_runs
    add column if not exists token_cost_est integer not null default 0;
alter table public.pipeline_runs
    add column if not exists evidence_score_bucket text not null default '';

-- Indexes
create index if not exists idx_pipeline_runs_approval_nonce
    on public.pipeline_runs (approval_nonce)
    where approval_nonce != '';
create index if not exists idx_pipeline_runs_video_created
    on public.pipeline_runs (video_id, created_at desc);

-- updated_at trigger (column already exists in 005)
do $$
begin
    if not exists (
        select 1 from pg_trigger
        where tgname = 'trg_pipeline_runs_updated_at'
          and tgrelid = 'public.pipeline_runs'::regclass
    ) then
        create trigger trg_pipeline_runs_updated_at
            before update on public.pipeline_runs
            for each row execute function public.set_updated_at();
    end if;
end
$$;

-- ==========================================================================
-- 2. run_events — atomic, idempotent audit trail
-- ==========================================================================

create table if not exists public.run_events (
    id              bigint generated always as identity primary key,
    run_id          uuid        not null
                    references public.pipeline_runs(id) on delete cascade,
    action_id       text        not null default '',
    event_type      text        not null default ''
                    check (event_type in (
                        'cb_pause',
                        'cb_auto_refetch',
                        'cb_healed',
                        'cb_alert',
                        'user_approval',
                        'user_ignore',
                        'user_abort',
                        'user_refetch',
                        'status_change',
                        'context_snapshot',
                        'fingerprint_change',
                        'conflict_detected',
                        'error'
                    )),
    payload         jsonb       not null default '{}',
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create unique index if not exists idx_run_events_idempotent
    on public.run_events (run_id, action_id)
    where action_id != '';
create index if not exists idx_run_events_run_id
    on public.run_events (run_id);
create index if not exists idx_run_events_event_type
    on public.run_events (event_type);
create index if not exists idx_run_events_created_at
    on public.run_events (created_at desc);

-- RLS: deny anon + authenticated. Backend uses service_role key (bypass).
alter table public.run_events enable row level security;
drop policy if exists "deny anon run_events" on public.run_events;
create policy "deny anon run_events" on public.run_events
    for all to anon using (false) with check (false);
drop policy if exists "deny authenticated run_events" on public.run_events;
create policy "deny authenticated run_events" on public.run_events
    for all to authenticated using (false) with check (false);

-- ==========================================================================
-- 3. evidence_items — shared evidence cache (raw facts + origin + TTL)
-- ==========================================================================

create table if not exists public.evidence_items (
    id              bigint generated always as identity primary key,
    normalized_id   text        not null default '',
    asin            text        not null default '',
    claim_type      text        not null default '',
    trust_tier      integer     not null default 3
                    check (trust_tier between 1 and 5),
    confidence      numeric(4,3) not null default 0,
    value           jsonb       not null default '{}',
    value_hash      text        not null default '',
    source_url      text        not null default '',
    source_name     text        not null default '',
    source_type     text        not null default '',
    reason_flags    text[]      not null default '{}',
    fetched_at      timestamptz not null default now(),
    expires_at      timestamptz,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

-- Core lookups
create index if not exists idx_evidence_items_asin_claim
    on public.evidence_items (asin, claim_type);
-- Conflict detection: high-trust evidence per product+claim, newest first
create index if not exists idx_evidence_nid_claim_fetched
    on public.evidence_items (normalized_id, claim_type, fetched_at desc);
-- TTL expiration checks
create index if not exists idx_evidence_items_expires
    on public.evidence_items (expires_at)
    where expires_at is not null;
-- Stats temporal window
create index if not exists idx_evidence_items_fetched_at
    on public.evidence_items (fetched_at desc);
-- Fast filter for Tier 4/5 conflict detection
create index if not exists idx_evidence_tier4plus
    on public.evidence_items (normalized_id, claim_type, fetched_at desc)
    where trust_tier >= 4;

-- updated_at trigger
do $$
begin
    if not exists (
        select 1 from pg_trigger
        where tgname = 'trg_evidence_items_updated_at'
          and tgrelid = 'public.evidence_items'::regclass
    ) then
        create trigger trg_evidence_items_updated_at
            before update on public.evidence_items
            for each row execute function public.set_updated_at();
    end if;
end
$$;

-- RLS: deny anon + authenticated
alter table public.evidence_items enable row level security;
drop policy if exists "deny anon evidence_items" on public.evidence_items;
create policy "deny anon evidence_items" on public.evidence_items
    for all to anon using (false) with check (false);
drop policy if exists "deny authenticated evidence_items" on public.evidence_items;
create policy "deny authenticated evidence_items" on public.evidence_items
    for all to authenticated using (false) with check (false);

-- ==========================================================================
-- 4. product_fingerprints — SKU consistency tracking
-- ==========================================================================

create table if not exists public.product_fingerprints (
    id              bigint generated always as identity primary key,
    asin            text        not null,
    normalized_id   text        not null default '',
    brand           text        not null default '',
    model_number    text        not null default '',
    ean_upc         text        not null default '',
    variant_attrs   jsonb       not null default '{}',
    title_hash      text        not null default '',
    fingerprint_hash text       not null default '',
    first_seen_at   timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create unique index if not exists idx_product_fingerprints_asin
    on public.product_fingerprints (asin);

-- updated_at trigger
do $$
begin
    if not exists (
        select 1 from pg_trigger
        where tgname = 'trg_product_fingerprints_updated_at'
          and tgrelid = 'public.product_fingerprints'::regclass
    ) then
        create trigger trg_product_fingerprints_updated_at
            before update on public.product_fingerprints
            for each row execute function public.set_updated_at();
    end if;
end
$$;

-- RLS: deny anon + authenticated
alter table public.product_fingerprints enable row level security;
drop policy if exists "deny anon product_fingerprints" on public.product_fingerprints;
create policy "deny anon product_fingerprints" on public.product_fingerprints
    for all to anon using (false) with check (false);
drop policy if exists "deny authenticated product_fingerprints" on public.product_fingerprints;
create policy "deny authenticated product_fingerprints" on public.product_fingerprints
    for all to authenticated using (false) with check (false);

-- ==========================================================================
-- 5. run_evidence — per-run forensic scoring (separates cache from usage)
-- ==========================================================================
-- evidence_items = shared cache (raw facts + origin + TTL)
-- run_evidence = per-run forensic record (score as computed in THAT run)

create table if not exists public.run_evidence (
    id              bigint generated always as identity primary key,
    run_id          uuid        not null
                    references public.pipeline_runs(id) on delete cascade,
    evidence_id     bigint      not null,
    constraint run_evidence_evidence_id_restrict
                    foreign key (evidence_id)
                    references public.evidence_items(id) on delete restrict,
    score_at_run    numeric(6,2) not null default 0,
    freshness_at_run numeric(4,3) not null default 0,
    policy_version  text        not null default '',
    used_for_claim_type text    not null default '',
    manual_override boolean     not null default false,
    override_reason text        not null default '',
    created_at      timestamptz not null default now()
);

-- Prevent duplicate evidence per run (idempotent inserts)
create unique index if not exists idx_run_evidence_unique
    on public.run_evidence (run_id, evidence_id);
create index if not exists idx_run_evidence_evidence_id
    on public.run_evidence (evidence_id);
create index if not exists idx_run_evidence_claim
    on public.run_evidence (used_for_claim_type);

-- RLS: deny anon + authenticated
alter table public.run_evidence enable row level security;
drop policy if exists "deny anon run_evidence" on public.run_evidence;
create policy "deny anon run_evidence" on public.run_evidence
    for all to anon using (false) with check (false);
drop policy if exists "deny authenticated run_evidence" on public.run_evidence;
create policy "deny authenticated run_evidence" on public.run_evidence
    for all to authenticated using (false) with check (false);

-- ==========================================================================
-- 6. Helper function: atomic CAS update for approval gate
-- ==========================================================================

create or replace function public.cas_run_status(
    p_run_id         uuid,
    p_expected_status text,
    p_expected_nonce  text,
    p_new_status      text,
    p_new_snapshot    jsonb default null,
    p_approved_by     text default ''
) returns boolean
language plpgsql
security definer
as $$
declare
    rows_affected int;
begin
    update public.pipeline_runs
    set status           = p_new_status,
        approval_nonce   = case when p_new_status = 'waiting_approval'
                                then p_expected_nonce
                                else '' end,
        context_snapshot = coalesce(p_new_snapshot, context_snapshot)
        -- updated_at handled by trigger
    where id = p_run_id
      and status = p_expected_status
      and (p_expected_nonce = '' or approval_nonce = p_expected_nonce);

    get diagnostics rows_affected = row_count;
    return rows_affected > 0;
end;
$$;
