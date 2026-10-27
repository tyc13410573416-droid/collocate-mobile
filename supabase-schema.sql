-- Supabase SQL Editor 中执行一次
create table if not exists public.collocate_states (
  sync_id text primary key,
  revision bigint not null default 0,
  state jsonb,
  updated_at timestamptz not null default now()
);

alter table public.collocate_states enable row level security;

drop policy if exists "collocate anon read" on public.collocate_states;
drop policy if exists "collocate anon insert" on public.collocate_states;
drop policy if exists "collocate anon update" on public.collocate_states;

-- 同步 ID 通过自定义请求头传入，避免 anon key 直接读到整张表。
create policy "collocate anon read" on public.collocate_states
  for select to anon
  using (sync_id = (current_setting('request.headers', true)::json ->> 'x-collocate-sync-id'));
create policy "collocate anon insert" on public.collocate_states
  for insert to anon
  with check (sync_id = (current_setting('request.headers', true)::json ->> 'x-collocate-sync-id'));
create policy "collocate anon update" on public.collocate_states
  for update to anon
  using (sync_id = (current_setting('request.headers', true)::json ->> 'x-collocate-sync-id'))
  with check (sync_id = (current_setting('request.headers', true)::json ->> 'x-collocate-sync-id'));

revoke all on table public.collocate_states from public;
grant select, insert, update on table public.collocate_states to anon;