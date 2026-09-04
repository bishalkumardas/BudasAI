-- The public website reads daily_news with the anon key.
-- Keep writes owned by the Admin app; expose only read access here.
alter table public.daily_news enable row level security;
drop policy if exists "Public can read daily news" on public.daily_news;
create policy "Public can read daily news"
  on public.daily_news
  for select
  to anon, authenticated
  using (true);
