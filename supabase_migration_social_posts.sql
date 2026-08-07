-- Run this once in your Supabase project's SQL Editor.
-- Adds the table used by the new Selenium-based Social Media Scraper
-- (Facebook, Instagram, YouTube, Threads, X/Twitter) -- see
-- app/services/social_scraper_service.py and pages/5_Social_Media_Scraper.py.

create table if not exists social_posts (
    id text primary key,
    platform text not null,
    author text,
    content text,
    url text,
    posted_at text,
    likes bigint,
    comments bigint,
    shares bigint,
    keyword text,
    created_at timestamptz not null default now()
);

create index if not exists idx_social_posts_platform on social_posts (platform);
create index if not exists idx_social_posts_keyword on social_posts (keyword);

-- If Row Level Security is enabled on your project (recommended), add
-- policies so the anon key used by the app can read/write this table,
-- e.g.:
-- alter table social_posts enable row level security;
-- create policy "allow anon all" on social_posts for all
--   using (true) with check (true);
