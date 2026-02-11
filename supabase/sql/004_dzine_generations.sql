-- Dzine image generation log
-- Run in Supabase SQL Editor after creating the dzine-assets storage bucket.

create table if not exists public.dzine_generations (
    id            bigint generated always as identity primary key,
    asset_type    text        not null,
    product_name  text        not null default '',
    style         text        not null default 'photorealistic',
    status        text        not null default 'success'
                              check (status in ('success', 'failed')),
    local_path    text        not null default '',
    storage_url   text        not null default '',
    checksum_sha256 text      not null default '',
    duration_s    numeric(8,2) not null default 0,
    error         text        not null default '',
    prompt_character text     not null default '',
    prompt_scene  text        not null default '',
    width         integer     not null default 0,
    height        integer     not null default 0,
    created_at    timestamptz not null default now()
);

comment on table public.dzine_generations is 'Log of Dzine image generation runs';

-- Indexes for common queries
create index if not exists idx_dzine_gen_asset_type on public.dzine_generations (asset_type);
create index if not exists idx_dzine_gen_status     on public.dzine_generations (status);
create index if not exists idx_dzine_gen_created_at on public.dzine_generations (created_at desc);

-- RLS: service role only (matches existing pattern)
alter table public.dzine_generations enable row level security;

create policy "Service role full access"
    on public.dzine_generations
    for all
    using (auth.role() = 'service_role')
    with check (auth.role() = 'service_role');

-- Grant read to authenticated users (for dashboards)
grant select on public.dzine_generations to authenticated;
grant all    on public.dzine_generations to service_role;
