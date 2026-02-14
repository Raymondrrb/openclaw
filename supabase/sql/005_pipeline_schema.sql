-- Rayviews pipeline schema: observability, research data, content, memory, analytics.
-- Run in Supabase SQL Editor after 004_dzine_generations.sql.
-- RLS on, service_role full access, authenticated read — matches existing pattern.

-- ==========================================================================
-- 1. pipeline_runs — one row per pipeline execution
-- ==========================================================================

create table if not exists public.pipeline_runs (
    id              uuid primary key default gen_random_uuid(),
    video_id        text        not null,
    status          text        not null default 'running'
                    check (status in ('running', 'complete', 'failed', 'aborted')),
    cluster         text        not null default '',
    micro_niche     jsonb       not null default '{}',
    config_snapshot jsonb       not null default '{}',
    stages_completed text[]     not null default '{}',
    error_code      text        not null default '',
    error_message   text        not null default '',
    elapsed_ms      integer     not null default 0,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create unique index if not exists idx_pipeline_runs_video_id on public.pipeline_runs (video_id);
create index if not exists idx_pipeline_runs_created_at on public.pipeline_runs (created_at desc);
create index if not exists idx_pipeline_runs_status on public.pipeline_runs (status);

alter table public.pipeline_runs enable row level security;
create policy "Service role full access" on public.pipeline_runs for all
    using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
grant select on public.pipeline_runs to authenticated;
grant all    on public.pipeline_runs to service_role;

-- ==========================================================================
-- 2. niches — niche selection metadata
-- ==========================================================================

create table if not exists public.niches (
    id              bigint generated always as identity primary key,
    run_id          uuid        references public.pipeline_runs(id) on delete cascade,
    video_id        text        not null default '',
    cluster         text        not null default '',
    subcategory     text        not null default '',
    buyer_pain      text        not null default '',
    intent_phrase   text        not null default '',
    price_min       integer     not null default 0,
    price_max       integer     not null default 0,
    must_have_features jsonb    not null default '[]',
    forbidden_variants jsonb    not null default '[]',
    gap_score       numeric(6,2) not null default 0,
    total_score     numeric(6,2) not null default 0,
    candidate_set   jsonb       not null default '[]',
    chosen_reason   text        not null default '',
    created_at      timestamptz not null default now()
);

create index if not exists idx_niches_run_id on public.niches (run_id);

alter table public.niches enable row level security;
create policy "Service role full access" on public.niches for all
    using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
grant select on public.niches to authenticated;
grant all    on public.niches to service_role;

-- ==========================================================================
-- 3. research_sources — pages browsed during research
-- ==========================================================================

create table if not exists public.research_sources (
    id              bigint generated always as identity primary key,
    run_id          uuid        references public.pipeline_runs(id) on delete cascade,
    source_domain   text        not null default '',
    source_url      text        not null default '',
    extraction      jsonb       not null default '{}',
    checksum        text        not null default '',
    ok              boolean     not null default true,
    error           text        not null default '',
    created_at      timestamptz not null default now()
);

create index if not exists idx_research_sources_run_id on public.research_sources (run_id);
create index if not exists idx_research_sources_domain on public.research_sources (source_domain);

alter table public.research_sources enable row level security;
create policy "Service role full access" on public.research_sources for all
    using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
grant select on public.research_sources to authenticated;
grant all    on public.research_sources to service_role;

-- ==========================================================================
-- 4. shortlist_items — products shortlisted from research
-- ==========================================================================

create table if not exists public.shortlist_items (
    id              bigint generated always as identity primary key,
    run_id          uuid        references public.pipeline_runs(id) on delete cascade,
    product_name_clean text     not null default '',
    candidate_rank  integer     not null default 0
                    check (candidate_rank between 1 and 7),
    buyer_pain_fit  text        not null default '',
    claims          jsonb       not null default '[]',
    downsides       jsonb       not null default '[]',
    evidence_by_source jsonb    not null default '{}',
    passed_domain_policy boolean not null default true,
    notes           text        not null default '',
    created_at      timestamptz not null default now()
);

create unique index if not exists idx_shortlist_items_unique
    on public.shortlist_items (run_id, product_name_clean);

alter table public.shortlist_items enable row level security;
create policy "Service role full access" on public.shortlist_items for all
    using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
grant select on public.shortlist_items to authenticated;
grant all    on public.shortlist_items to service_role;

-- ==========================================================================
-- 5. amazon_products — verified products on Amazon US
-- ==========================================================================

create table if not exists public.amazon_products (
    id              bigint generated always as identity primary key,
    run_id          uuid        references public.pipeline_runs(id) on delete cascade,
    asin            text        not null default '',
    amazon_title    text        not null default '',
    price           numeric(10,2),
    rating          numeric(3,2),
    review_count    integer     not null default 0,
    in_stock        boolean     not null default true,
    pdp_url         text        not null default '',
    affiliate_short_url text    not null default '',
    verified_at     timestamptz not null default now(),
    rejected        boolean     not null default false,
    reject_reason   text        not null default '',
    created_at      timestamptz not null default now()
);

create index if not exists idx_amazon_products_run_id on public.amazon_products (run_id);
create index if not exists idx_amazon_products_asin on public.amazon_products (asin);

alter table public.amazon_products enable row level security;
create policy "Service role full access" on public.amazon_products for all
    using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
grant select on public.amazon_products to authenticated;
grant all    on public.amazon_products to service_role;

-- ==========================================================================
-- 6. top5 — final ranked products
-- ==========================================================================

create table if not exists public.top5 (
    id              bigint generated always as identity primary key,
    run_id          uuid        references public.pipeline_runs(id) on delete cascade,
    rank            integer     not null check (rank between 1 and 5),
    asin            text        not null default '',
    role_label      text        not null default '',
    benefits        jsonb       not null default '[]',
    downside        text        not null default '',
    source_evidence jsonb       not null default '[]',
    affiliate_short_url text    not null default '',
    price           numeric(10,2),
    created_at      timestamptz not null default now()
);

create unique index if not exists idx_top5_run_rank on public.top5 (run_id, rank);
create unique index if not exists idx_top5_run_asin on public.top5 (run_id, asin);

alter table public.top5 enable row level security;
create policy "Service role full access" on public.top5 for all
    using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
grant select on public.top5 to authenticated;
grant all    on public.top5 to service_role;

-- ==========================================================================
-- 7. scripts — script generation stages
-- ==========================================================================

create table if not exists public.scripts (
    id              bigint generated always as identity primary key,
    run_id          uuid        references public.pipeline_runs(id) on delete cascade,
    brief_text      text        not null default '',
    script_raw      text        not null default '',
    review_notes    text        not null default '',
    script_final    text        not null default '',
    word_count      integer     not null default 0,
    has_disclosure  boolean     not null default false,
    status          text        not null default 'draft'
                    check (status in ('draft', 'brief', 'raw', 'reviewed', 'final', 'approved')),
    created_at      timestamptz not null default now()
);

create index if not exists idx_scripts_run_id on public.scripts (run_id);

alter table public.scripts enable row level security;
create policy "Service role full access" on public.scripts for all
    using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
grant select on public.scripts to authenticated;
grant all    on public.scripts to service_role;

-- ==========================================================================
-- 8. assets — generated images
-- ==========================================================================

create table if not exists public.assets (
    id              bigint generated always as identity primary key,
    run_id          uuid        references public.pipeline_runs(id) on delete cascade,
    asset_type      text        not null default '',
    product_asin    text        not null default '',
    prompt          text        not null default '',
    style_rules_version text    not null default '',
    storage_path    text        not null default '',
    width           integer     not null default 0,
    height          integer     not null default 0,
    ok              boolean     not null default true,
    error           text        not null default '',
    created_at      timestamptz not null default now()
);

create index if not exists idx_assets_run_id on public.assets (run_id);

alter table public.assets enable row level security;
create policy "Service role full access" on public.assets for all
    using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
grant select on public.assets to authenticated;
grant all    on public.assets to service_role;

-- ==========================================================================
-- 9. tts_audio — voiceover chunks
-- ==========================================================================

create table if not exists public.tts_audio (
    id              bigint generated always as identity primary key,
    run_id          uuid        references public.pipeline_runs(id) on delete cascade,
    chunk_index     integer     not null default 0,
    text            text        not null default '',
    voice_id        text        not null default '',
    model           text        not null default '',
    storage_path    text        not null default '',
    duration_seconds numeric(8,2) not null default 0,
    ok              boolean     not null default true,
    error           text        not null default '',
    created_at      timestamptz not null default now()
);

create index if not exists idx_tts_audio_run_id on public.tts_audio (run_id);

alter table public.tts_audio enable row level security;
create policy "Service role full access" on public.tts_audio for all
    using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
grant select on public.tts_audio to authenticated;
grant all    on public.tts_audio to service_role;

-- ==========================================================================
-- 10. agent_events — inter-agent message log
-- ==========================================================================

create table if not exists public.agent_events (
    id              bigint generated always as identity primary key,
    run_id          uuid        references public.pipeline_runs(id) on delete cascade,
    stage           text        not null default '',
    agent_name      text        not null default '',
    event_type      text        not null default '',
    payload         jsonb       not null default '{}',
    created_at      timestamptz not null default now()
);

create index if not exists idx_agent_events_run_id on public.agent_events (run_id);
create index if not exists idx_agent_events_stage on public.agent_events (stage);

alter table public.agent_events enable row level security;
create policy "Service role full access" on public.agent_events for all
    using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
grant select on public.agent_events to authenticated;
grant all    on public.agent_events to service_role;

-- ==========================================================================
-- 11. lessons — learned from errors and reviews
-- ==========================================================================

create table if not exists public.lessons (
    id              bigint generated always as identity primary key,
    scope           text        not null default '',
    trigger         text        not null default '',
    rule            text        not null default '',
    example         jsonb       not null default '{}',
    severity        text        not null default 'med'
                    check (severity in ('low', 'med', 'high')),
    active          boolean     not null default true,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create unique index if not exists idx_lessons_scope_trigger
    on public.lessons (scope, trigger);

alter table public.lessons enable row level security;
create policy "Service role full access" on public.lessons for all
    using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
grant select on public.lessons to authenticated;
grant all    on public.lessons to service_role;

-- ==========================================================================
-- 12. channel_memory — persistent key-value store
-- ==========================================================================

create table if not exists public.channel_memory (
    key             text primary key,
    value           jsonb       not null default '{}',
    updated_at      timestamptz not null default now()
);

alter table public.channel_memory enable row level security;
create policy "Service role full access" on public.channel_memory for all
    using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
grant select on public.channel_memory to authenticated;
grant all    on public.channel_memory to service_role;

-- ==========================================================================
-- 13. video_metrics — YouTube performance feedback
-- ==========================================================================

create table if not exists public.video_metrics (
    id              bigint generated always as identity primary key,
    video_id        text        not null default '',
    youtube_id      text        not null default '',
    niche           text        not null default '',
    views_24h       integer,
    views_48h       integer,
    views_7d        integer,
    views_30d       integer,
    ctr             numeric(5,2),
    avd_seconds     integer,
    avg_view_percent numeric(5,2),
    affiliate_clicks integer,
    conversions     integer,
    rpm_estimate    numeric(8,2),
    recorded_at     timestamptz not null default now()
);

create index if not exists idx_video_metrics_video_id on public.video_metrics (video_id);
create index if not exists idx_video_metrics_niche on public.video_metrics (niche);
create index if not exists idx_video_metrics_recorded_at on public.video_metrics (recorded_at desc);

alter table public.video_metrics enable row level security;
create policy "Service role full access" on public.video_metrics for all
    using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
grant select on public.video_metrics to authenticated;
grant all    on public.video_metrics to service_role;

-- ==========================================================================
-- Storage buckets (create via Supabase Dashboard > Storage):
--   1. rayviews-assets   — Dzine images + Amazon refs
--   2. rayviews-audio    — TTS voiceover chunks
--   3. rayviews-manifests — Resolve manifests, markers, notes
-- ==========================================================================
