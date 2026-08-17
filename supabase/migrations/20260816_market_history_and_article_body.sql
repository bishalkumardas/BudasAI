-- Run this once in the Supabase SQL Editor for an existing project.
create index if not exists market_history_market_timestamp_idx
  on public.market_history (market_id, timestamp);

alter table public.research_articles
  add column if not exists body_html text not null default '';
