-- Run this once in your Supabase project's SQL Editor.
-- Adds the two tables the updated Scraping & Fenomena pages depend on.

create table if not exists executive_summaries (
    id bigint generated always as identity primary key,
    kata_kunci text not null,
    rentang_waktu text,
    hasil_summary text not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_executive_summaries_kata_kunci
    on executive_summaries (kata_kunci);

create table if not exists root_cause_analysis (
    id bigint generated always as identity primary key,
    initial_query text not null,
    result_tree jsonb not null,
    executive_summary text,
    created_at timestamptz not null default now()
);

create index if not exists idx_root_cause_analysis_query
    on root_cause_analysis (initial_query);

-- If Row Level Security is enabled on your project (recommended), add
-- policies so the anon key used by the app can read/write these tables,
-- e.g.:
-- alter table executive_summaries enable row level security;
-- create policy "allow anon all" on executive_summaries for all
--   using (true) with check (true);
-- alter table root_cause_analysis enable row level security;
-- create policy "allow anon all" on root_cause_analysis for all
--   using (true) with check (true);
