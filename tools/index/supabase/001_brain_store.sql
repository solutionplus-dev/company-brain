-- 001_brain_store.sql — the brain store in your Supabase project.
--
-- Idempotent: safe to run again. Run it as the project's owner role (postgres) in the SQL editor
-- or through a reviewed apply step. It creates only objects named brain_* in
-- schema public and touches nothing else there.
--
-- Why public with a brain_ prefix and not a schema "brain": PostgREST serves only the schemas
-- listed under "Exposed schemas" in the dashboard (API settings). A new schema would need that
-- dashboard change before the sync script could write a single row; public is exposed by default.
-- Exposure is not access: every brain_* table below has row-level security enabled AND forced,
-- no policy at all for anon, all privileges revoked from anon and PUBLIC, read-only for
-- authenticated (scope-filtered), and writes only for service_role.
--
-- Access model (fails closed):
--   anon            no table privilege, no policy, no function execute.  -> nothing.
--   authenticated   SELECT only, and only rows whose scope is in public.brain_members.scopes
--                   for auth.uid(). Unknown user -> empty scope list -> zero rows.
--   service_role    bypasses RLS (Supabase role attribute); the only role that writes.
--
-- Scopes: finance, ops (owner only), gtm, outreach, templates, design (team), client:<slug>.

begin;

create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------- scope type

do $$
begin
  if not exists (
    select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
    where n.nspname = 'public' and t.typname = 'brain_scope'
  ) then
    create domain public.brain_scope as text
      constraint brain_scope_format
      check (value ~ '^(finance|ops|gtm|outreach|templates|design|client:[a-z0-9][a-z0-9_-]{0,62})$');
  end if;
end $$;

comment on domain public.brain_scope is
  'Brain access scope. finance and ops: owner only. gtm, outreach, templates, design: the team. '
  'client:<slug>: the people on that client project. Granted per user in public.brain_members.';

-- ---------------------------------------------------------------- tables

create table if not exists public.brain_documents (
  id          uuid primary key,
  scope       public.brain_scope not null,
  module      text not null check (module ~ '^[a-z0-9][a-z0-9_-]{0,63}$'),
  source      text not null default 'vault' check (source ~ '^[a-z0-9][a-z0-9_.-]{0,63}$'),
  path        text not null check (length(path) between 1 and 1024),
  sha256      text check (sha256 ~ '^[0-9a-f]{64}$'),
  text_key    text check (text_key ~ '^[0-9a-f]{64}$'),
  redaction   text,
  title       text,
  area        text,
  tier        text,
  company     text check (company ~ '^[A-Za-z][A-Za-z0-9_-]{0,15}$'),
  doc_date    text check (doc_date ~ '^[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?$'),
  has_digest  boolean not null default false,
  size        bigint check (size >= 0),
  n_chunks    integer not null default 0 check (n_chunks >= 0),
  updated_at  timestamptz,
  synced_at   timestamptz not null default now(),
  constraint brain_documents_scope_path_key unique (scope, path),
  constraint brain_documents_id_scope_key unique (id, scope)
);

create table if not exists public.brain_chunks (
  id          uuid primary key,
  document_id uuid not null,
  scope       public.brain_scope not null,
  ord         integer not null check (ord >= 0),
  text        text not null check (length(text) <= 20000),
  tsv         tsvector generated always as (to_tsvector('simple'::regconfig, text)) stored,
  constraint brain_chunks_document_ord_key unique (document_id, ord),
  constraint brain_chunks_id_scope_key unique (id, scope),
  -- composite key: a chunk can never carry a different scope from its document
  constraint brain_chunks_document_fk foreign key (document_id, scope)
    references public.brain_documents (id, scope) on delete cascade
);

create table if not exists public.brain_embeddings (
  chunk_id    uuid primary key,
  scope       public.brain_scope not null,
  bin         bit(768) not null,
  "full"      extensions.halfvec(768) not null,
  model       text not null,
  constraint brain_embeddings_chunk_fk foreign key (chunk_id, scope)
    references public.brain_chunks (id, scope) on delete cascade
);

create table if not exists public.brain_records (
  id           uuid primary key,
  scope        public.brain_scope not null,
  source       text not null default 'vault' check (source ~ '^[a-z0-9][a-z0-9_.-]{0,63}$'),
  kind         text not null,
  company      text check (company ~ '^[A-Za-z][A-Za-z0-9_-]{0,15}$'),
  ref          text,
  title        text,
  date         text,
  due_date     text,
  amount       numeric,
  amount_text  text,
  currency     text,
  counterparty text,
  status       text,
  certainty    text,
  client       text,
  account      text,
  debit        numeric,
  credit       numeric,
  source_path  text not null,
  source_line  integer,
  extra        jsonb,
  synced_at    timestamptz not null default now(),
  constraint brain_records_natural_key unique (scope, kind, ref, source_path, source_line),
  -- a ledger line always belongs to exactly one company and one currency, so it can never be
  -- summed across legal entities or across currencies by accident
  constraint brain_records_ledger_shape check (
    kind <> 'ledger_line'
    or (company is not null and company not in ('both', 'none') and currency ~ '^[A-Z]{3}$')
  )
);

create table if not exists public.brain_edges (
  id     uuid primary key,
  scope  public.brain_scope not null,
  source text not null default 'vault' check (source ~ '^[a-z0-9][a-z0-9_.-]{0,63}$'),
  src    text not null,
  dst    text not null,
  rel    text not null,
  constraint brain_edges_natural_key unique (scope, src, dst, rel)
);

create table if not exists public.brain_sync_runs (
  id               bigint generated always as identity primary key,
  scope            public.brain_scope not null,
  source           text,
  module           text,
  mode             text not null,
  tool_version     text,
  started_at       timestamptz not null default now(),
  finished_at      timestamptz,
  status           text not null default 'running' check (status in ('running', 'ok', 'failed')),
  documents        integer,
  chunks           integer,
  embeddings       integer,
  records          integer,
  edges            integer,
  deleted          integer,
  blocked          integer,
  redacted_chunks  integer,
  note             text
);

create table if not exists public.brain_members (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  scopes     public.brain_scope[] not null default '{}',
  note       text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- indexes

create index if not exists brain_documents_source_idx on public.brain_documents (scope, source);
create index if not exists brain_records_source_idx   on public.brain_records (scope, source);
create index if not exists brain_chunks_scope_idx      on public.brain_chunks (scope);
create index if not exists brain_chunks_tsv_gin        on public.brain_chunks using gin (tsv);
create index if not exists brain_embeddings_scope_idx  on public.brain_embeddings (scope);
create index if not exists brain_embeddings_bin_hnsw   on public.brain_embeddings
  using hnsw (bin extensions.bit_hamming_ops);
create index if not exists brain_records_scope_kind_idx on public.brain_records (scope, kind, company, status);
create index if not exists brain_records_due_idx       on public.brain_records (scope, due_date);
create index if not exists brain_edges_src_idx         on public.brain_edges (scope, src);
create index if not exists brain_edges_dst_idx         on public.brain_edges (scope, dst);
create index if not exists brain_sync_runs_scope_idx   on public.brain_sync_runs (scope, started_at desc);

-- ---------------------------------------------------------------- comments

comment on table public.brain_documents is
  'Brain store: one row per file of a brain module (metadata only, never file bytes), unique on '
  '(scope, path); source names the brain that wrote it (vault, gtm-brain, ...). Filled only by '
  'tools/index/supabase_sync.py from the owner''s local index. Scopes: finance, ops (owner only); '
  'gtm, outreach, templates, design (team); client:<slug> (that project''s people).';
comment on table public.brain_chunks is
  'Brain store: redacted text passages of a document (same scope as its document, enforced by a '
  'composite foreign key), with a full-text vector. Scopes as in brain_documents.';
comment on table public.brain_embeddings is
  'Brain store: one 768-dimension embedding per chunk (EmbeddingGemma 2): bin = sign bits for the '
  'Hamming first pass (HNSW, bit_hamming_ops), full = half-precision unit vector for re-scoring. '
  'Scopes as in brain_documents.';
comment on table public.brain_records is
  'Brain store: business objects (ledger_line, invoice, expense, balance, open_item, ruling, '
  'invoice_register, deadline, meeting, decision, ...), copied as written from the local records '
  'table, unique on scope + the local natural key. ledger_line uses account / debit / credit and '
  'must name one legal entity and one currency; read ledgers through brain_ledger(entity code). '
  'Never sum across entities or currencies. Scopes as in brain_documents.';
comment on table public.brain_edges is
  'Brain store: links between files and records inside one scope (digest_of, in_folder, ...).';
comment on table public.brain_sync_runs is
  'Brain store: one row per sync run and scope (counts only, never content).';
comment on table public.brain_members is
  'Brain store: which signed-in user may read which scopes. Edited by the owner only (SQL editor '
  'or service role). Scopes: finance, ops, gtm, outreach, templates, design, client:<slug>.';
comment on column public.brain_embeddings."full" is
  'Unit vector, half precision; dot product = cosine similarity.';

-- ---------------------------------------------------------------- helper: caller's scopes

create or replace function public.brain_current_scopes()
returns text[]
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(
    (select m.scopes::text[] from public.brain_members m where m.user_id = (select auth.uid())),
    '{}'::text[]
  )
$$;

comment on function public.brain_current_scopes() is
  'Scopes the calling signed-in user holds (public.brain_members for auth.uid()); empty for anyone '
  'else. Security definer so members need no read access to the whole table.';

-- ---------------------------------------------------------------- row-level security

alter table public.brain_documents   enable row level security;
alter table public.brain_chunks      enable row level security;
alter table public.brain_embeddings  enable row level security;
alter table public.brain_records     enable row level security;
alter table public.brain_edges       enable row level security;
alter table public.brain_sync_runs   enable row level security;
alter table public.brain_members     enable row level security;

alter table public.brain_documents   force row level security;
alter table public.brain_chunks      force row level security;
alter table public.brain_embeddings  force row level security;
alter table public.brain_records     force row level security;
alter table public.brain_edges       force row level security;
alter table public.brain_sync_runs   force row level security;
alter table public.brain_members     force row level security;

drop policy if exists brain_documents_read  on public.brain_documents;
drop policy if exists brain_chunks_read     on public.brain_chunks;
drop policy if exists brain_embeddings_read on public.brain_embeddings;
drop policy if exists brain_records_read    on public.brain_records;
drop policy if exists brain_edges_read      on public.brain_edges;
drop policy if exists brain_sync_runs_read  on public.brain_sync_runs;
drop policy if exists brain_members_own_row on public.brain_members;

create policy brain_documents_read on public.brain_documents
  for select to authenticated using (scope::text = any ((select public.brain_current_scopes())::text[]));
create policy brain_chunks_read on public.brain_chunks
  for select to authenticated using (scope::text = any ((select public.brain_current_scopes())::text[]));
create policy brain_embeddings_read on public.brain_embeddings
  for select to authenticated using (scope::text = any ((select public.brain_current_scopes())::text[]));
create policy brain_records_read on public.brain_records
  for select to authenticated using (scope::text = any ((select public.brain_current_scopes())::text[]));
create policy brain_edges_read on public.brain_edges
  for select to authenticated using (scope::text = any ((select public.brain_current_scopes())::text[]));
create policy brain_sync_runs_read on public.brain_sync_runs
  for select to authenticated using (scope::text = any ((select public.brain_current_scopes())::text[]));
create policy brain_members_own_row on public.brain_members
  for select to authenticated using (user_id = (select auth.uid()));

-- FORCE also binds the table owner. The security-definer helper and the nightly health job
-- (003_cron.sql) run as that owner, so the owner role (whoever applies this file, normally
-- postgres) gets an explicit read policy on every brain table. It could read them anyway: as owner
-- it can switch RLS off. No other role gets such a policy.
do $$
declare t text;
begin
  foreach t in array array['brain_documents', 'brain_chunks', 'brain_embeddings', 'brain_records',
                           'brain_edges', 'brain_sync_runs', 'brain_members']
  loop
    if not exists (
      select 1 from pg_policies
      where schemaname = 'public' and tablename = t and policyname = t || '_owner_read'
    ) then
      execute format('create policy %I on public.%I for select to %I using (true)',
                     t || '_owner_read', t, current_user);
    end if;
  end loop;
end $$;

-- ---------------------------------------------------------------- privileges

revoke all on table
  public.brain_documents, public.brain_chunks, public.brain_embeddings, public.brain_records,
  public.brain_edges, public.brain_sync_runs, public.brain_members
  from public, anon, authenticated;

grant select on table
  public.brain_documents, public.brain_chunks, public.brain_embeddings, public.brain_records,
  public.brain_edges, public.brain_sync_runs
  to authenticated;
grant select (user_id, scopes) on table public.brain_members to authenticated;

grant select, insert, update, delete on table
  public.brain_documents, public.brain_chunks, public.brain_embeddings, public.brain_records,
  public.brain_edges, public.brain_sync_runs, public.brain_members
  to service_role;

do $$
declare s text := pg_get_serial_sequence('public.brain_sync_runs', 'id');
begin
  execute format('revoke all on sequence %s from public, anon, authenticated', s);
  execute format('grant usage, select on sequence %s to service_role', s);
end $$;

revoke all on function public.brain_current_scopes() from public, anon;
grant execute on function public.brain_current_scopes() to authenticated, service_role;

-- ---------------------------------------------------------------- ledger (one legal entity per call)

-- One function instead of a table anybody can sum: the caller must name ONE legal entity, so a mixed
-- ledger cannot be read by accident. security invoker: the RLS scope filter of brain_records applies.
create or replace function public.brain_ledger(p_company text)
returns table (id uuid, scope public.brain_scope, ref text, title text, date text, account text,
               debit numeric, credit numeric, amount numeric, amount_text text, currency text,
               counterparty text, status text, certainty text, client text, source_path text,
               source_line integer, extra jsonb, synced_at timestamptz)
language sql stable security invoker set search_path = ''
as $$
  select r.id, r.scope, r.ref, r.title, r.date, r.account, r.debit, r.credit, r.amount,
         r.amount_text, r.currency, r.counterparty, r.status, r.certainty, r.client,
         r.source_path, r.source_line, r.extra, r.synced_at
  from public.brain_records r
  where r.kind = 'ledger_line'
    and p_company is not null and p_company not in ('both', 'none')
    and r.company = p_company;
$$;
comment on function public.brain_ledger(text) is
  'Ledger lines of ONE legal entity (its code from brain.config.json), never converted. '
  'Sum per currency only. Scope finance.';

revoke all on function public.brain_ledger(text) from public, anon;
grant execute on function public.brain_ledger(text) to authenticated, service_role;

-- ---------------------------------------------------------------- search

-- Arguments are text, not bit(768) / halfvec(768): function parameters lose their type modifier,
-- and PostgREST rebuilds RPC arguments from the bare type name, which for "bit" means bit(1).
-- The function validates and casts them itself.
create or replace function public.brain_search(
  query_bin   text,
  query_full  text,
  query_text  text,
  k           integer default 20,
  want_scopes text[]  default null
)
returns table (
  document_id uuid,
  scope       text,
  module      text,
  path        text,
  title       text,
  chunk_ord   integer,
  snippet     text,
  score       double precision,
  vec_score   double precision,
  text_score  double precision
)
language plpgsql
volatile
security invoker
set search_path = ''
as $$
#variable_conflict use_column
declare
  v_caller text[];
  v_eff    text[];
  v_k      integer := least(greatest(coalesce(k, 20), 1), 100);
  v_pool   constant integer := 300;
  v_bin    bit(768);
  v_full   extensions.halfvec(768);
  v_tsq    tsquery;
begin
  -- 1. Which scopes may this call see? service_role: what it asks for (null = all).
  --    Everyone else: their own scopes, intersected with what they ask for. RLS applies on top.
  if current_user = 'service_role' then
    v_caller := null;
  else
    v_caller := public.brain_current_scopes();
  end if;

  if v_caller is null then
    v_eff := want_scopes;
  elsif want_scopes is null then
    v_eff := v_caller;
  else
    v_eff := array(select unnest(v_caller) intersect select unnest(want_scopes));
  end if;

  if v_eff is not null and cardinality(v_eff) = 0 then
    return;
  end if;

  -- 2. Query inputs.
  if query_bin is not null then
    if length(query_bin) <> 768 or query_bin !~ '^[01]+$' then
      raise exception 'query_bin must be 768 characters of 0 and 1' using errcode = '22023';
    end if;
    v_bin := query_bin::bit(768);
  end if;
  if query_full is not null then
    v_full := query_full::extensions.halfvec(768);
  end if;
  if nullif(btrim(coalesce(query_text, '')), '') is not null then
    v_tsq := websearch_to_tsquery('simple'::regconfig, query_text);
    if numnode(v_tsq) = 0 then
      v_tsq := null;
    end if;
  end if;
  if v_bin is null and v_tsq is null then
    return;
  end if;

  perform set_config('hnsw.ef_search', '400', true);
  perform set_config('hnsw.iterative_scan', 'relaxed_order', true);

  -- 3. Hamming first pass on bin -> re-score with full -> fuse with full-text rank (RRF) ->
  --    best chunk per document.
  return query
  with vec_pool as (
    select e.chunk_id,
           e."full" as fv,
           (e.bin operator(extensions.<~>) v_bin) as ham
    from public.brain_embeddings e
    where v_bin is not null
      and (v_eff is null or e.scope::text = any (v_eff))
    order by e.bin operator(extensions.<~>) v_bin
    limit v_pool
  ),
  vec as (
    select p.chunk_id,
           case when v_full is null then 1.0 - p.ham / 768.0
                else (-(p.fv operator(extensions.<#>) v_full))::double precision
           end as vs
    from vec_pool p
  ),
  vec_ranked as (
    select v.chunk_id, v.vs, row_number() over (order by v.vs desc) as r from vec v
  ),
  txt as (
    select c.id as chunk_id, ts_rank_cd(c.tsv, v_tsq)::double precision as ts
    from public.brain_chunks c
    where v_tsq is not null
      and c.tsv @@ v_tsq
      and (v_eff is null or c.scope::text = any (v_eff))
    order by 2 desc
    limit v_pool
  ),
  txt_ranked as (
    select t.chunk_id, t.ts, row_number() over (order by t.ts desc) as r from txt t
  ),
  fused as (
    select coalesce(v.chunk_id, t.chunk_id) as chunk_id,
           v.vs,
           t.ts,
           coalesce(1.0 / (60 + v.r), 0) + coalesce(1.0 / (60 + t.r), 0) as s
    from vec_ranked v
    full outer join txt_ranked t on t.chunk_id = v.chunk_id
  ),
  best as (
    select distinct on (c.document_id)
           c.document_id as doc_id, c.ord as c_ord, c.text as c_text, f.s, f.vs, f.ts
    from fused f
    join public.brain_chunks c on c.id = f.chunk_id
    where (v_eff is null or c.scope::text = any (v_eff))
    order by c.document_id, f.s desc
  )
  select d.id, d.scope::text, d.module, d.path, d.title, b.c_ord, left(b.c_text, 300),
         b.s::double precision, b.vs, b.ts
  from best b
  join public.brain_documents d on d.id = b.doc_id
  where (v_eff is null or d.scope::text = any (v_eff))
  order by b.s desc
  limit v_k;
end
$$;

comment on function public.brain_search(text, text, text, integer, text[]) is
  'Blended brain search. query_bin: 768 chars of 0/1 (sign bits); query_full: halfvec text '
  '''[x,...]'' (768 unit vector); query_text: words. Hamming first pass on the HNSW bit index, '
  're-score with the half-precision vector, fuse with full-text rank. Returns only scopes the caller '
  'holds (want_scopes intersected with public.brain_current_scopes(); service_role: all).';

revoke all on function public.brain_search(text, text, text, integer, text[]) from public, anon;
grant execute on function public.brain_search(text, text, text, integer, text[]) to authenticated, service_role;

commit;
