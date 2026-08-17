-- Run after resolving any existing duplicate (market_id, timestamp) rows.
-- This unique index makes the intended import identity enforceable and permits
-- a future upsert with on_conflict='market_id,timestamp'.
create unique index if not exists market_history_market_timestamp_key
  on public.market_history (market_id, timestamp);
