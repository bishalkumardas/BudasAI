-- Optional starter record. Add richer content through Supabase dashboard or migrations.
insert into public.markets (symbol,name,region,category,currency) values ('NIFTY','NIFTY 50','India','Index','INR') on conflict (symbol) do nothing;
insert into public.market_history (market_id,timestamp,value,volume)
select id, now(), 24821.35, null
from public.markets
where symbol = 'NIFTY'
  and not exists (
    select 1 from public.market_history
    where market_id = public.markets.id
  );
