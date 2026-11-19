-- 003_cron.sql — nightly upkeep of the brain store with pg_cron (1.6.x).
--
-- Apply after 001_brain_store.sql. Idempotent: every job is unscheduled by its fixed name and
-- scheduled again. Jobs run as the role that applies this file (the database owner, postgres).
-- No HTTP calls from the database. Times are UTC (pg_cron default).
--
--   brain_analyze_nightly        02:40  ANALYZE the brain tables
--   brain_health_refresh_nightly 02:50  rebuild public.brain_health
--   brain_prune_sync_runs_weekly 03:10 Sunday  delete brain_sync_runs rows older than 180 days

begin;

-- ---------------------------------------------------------------- health table

create table if not exists public.brain_health (
  scope                      public.brain_scope primary key,
  documents                  integer not null default 0,
  chunks                     integer not null default 0,
  embeddings                 integer not null default 0,
  records                    integer not null default 0,
  edges                      integer not null default 0,
  newest_synced_at           timestamptz,
  documents_without_chunks   integer not null default 0,
  chunks_without_embeddings  integer not null default 0,
  refreshed_at               timestamptz not null default now()
);

comment on table public.brain_health is
  'Brain store health per scope (counts only), rebuilt nightly by pg_cron job '
  'brain_health_refresh_nightly. documents_without_chunks includes images and binaries whose text '
  'lives in their digest document; chunks_without_embeddings > 0 means the vector step is behind.';

alter table public.brain_health enable row level security;
alter table public.brain_health force row level security;

drop policy if exists brain_health_read on public.brain_health;
create policy brain_health_read on public.brain_health
  for select to authenticated using (scope::text = any ((select public.brain_current_scopes())::text[]));

-- the refresh job runs as the owner role, which FORCE binds too: it needs to write here
do $$
begin
  if not exists (select 1 from pg_policies
                 where schemaname = 'public' and tablename = 'brain_health'
                   and policyname = 'brain_health_owner_all') then
    execute format('create policy brain_health_owner_all on public.brain_health for all to %I '
                   'using (true) with check (true)', current_user);
  end if;
  -- the weekly prune may delete only rows older than 180 days, nothing else
  if not exists (select 1 from pg_policies
                 where schemaname = 'public' and tablename = 'brain_sync_runs'
                   and policyname = 'brain_sync_runs_owner_prune') then
    execute format('create policy brain_sync_runs_owner_prune on public.brain_sync_runs for delete '
                   'to %I using (started_at < now() - interval ''180 days'')', current_user);
  end if;
end $$;

revoke all on table public.brain_health from public, anon, authenticated;
grant select on table public.brain_health to authenticated;
grant select, insert, update, delete on table public.brain_health to service_role;

-- ---------------------------------------------------------------- refresh function

create or replace function public.brain_refresh_health()
returns integer
language plpgsql
volatile
security invoker
set search_path = ''
as $$
declare n integer;
begin
  delete from public.brain_health where true;
  insert into public.brain_health (scope, documents, chunks, embeddings, records, edges,
                                   newest_synced_at, documents_without_chunks,
                                   chunks_without_embeddings, refreshed_at)
  with s as (
    select d.scope::text as scope from public.brain_documents d
    union select r.scope::text from public.brain_records r
    union select e.scope::text from public.brain_edges e
  )
  select s.scope,
         (select count(*) from public.brain_documents d where d.scope::text = s.scope),
         (select count(*) from public.brain_chunks c where c.scope::text = s.scope),
         (select count(*) from public.brain_embeddings e where e.scope::text = s.scope),
         (select count(*) from public.brain_records r where r.scope::text = s.scope),
         (select count(*) from public.brain_edges g where g.scope::text = s.scope),
         greatest((select max(d.synced_at) from public.brain_documents d where d.scope::text = s.scope),
                  (select max(r.synced_at) from public.brain_records r where r.scope::text = s.scope)),
         (select count(*) from public.brain_documents d
           where d.scope::text = s.scope
             and not exists (select 1 from public.brain_chunks c where c.document_id = d.id)),
         (select count(*) from public.brain_chunks c
           where c.scope::text = s.scope
             and not exists (select 1 from public.brain_embeddings e where e.chunk_id = c.id)),
         now()
  from s;
  get diagnostics n = row_count;
  return n;
end
$$;

comment on function public.brain_refresh_health() is
  'Rebuilds public.brain_health. Called nightly by pg_cron as the owner; not callable through the API.';

revoke all on function public.brain_refresh_health() from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------- jobs

select cron.unschedule(j.jobid)
from cron.job j
where j.jobname in ('brain_analyze_nightly', 'brain_health_refresh_nightly', 'brain_prune_sync_runs_weekly');

select cron.schedule(
  'brain_analyze_nightly',
  '40 2 * * *',
  $job$analyze public.brain_documents, public.brain_chunks, public.brain_embeddings,
               public.brain_records, public.brain_edges, public.brain_sync_runs,
               public.brain_members, public.brain_health$job$
);

select cron.schedule(
  'brain_health_refresh_nightly',
  '50 2 * * *',
  $job$select public.brain_refresh_health()$job$
);

select cron.schedule(
  'brain_prune_sync_runs_weekly',
  '10 3 * * 0',
  $job$delete from public.brain_sync_runs where started_at < now() - interval '180 days'$job$
);

commit;

-- Check (read-only):
--   select jobname, schedule, command, username, active from cron.job where jobname like 'brain\_%';
--   select jobid, status, return_message, start_time from cron.job_run_details
--     where jobid in (select jobid from cron.job where jobname like 'brain\_%')
--     order by start_time desc limit 20;
-- Remove the jobs:
--   select cron.unschedule(jobid) from cron.job where jobname like 'brain\_%';
