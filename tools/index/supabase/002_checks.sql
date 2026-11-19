-- 002_checks.sql — read-only checks to run after 001_brain_store.sql (and 003_cron.sql).
-- Every block is a SELECT, or a transaction that is rolled back. Expected results are noted.

-- 1. Extension. Expect: vector 0.8.x in schema extensions.
select e.extname, e.extversion, n.nspname as schema
from pg_extension e join pg_namespace n on n.oid = e.extnamespace
where e.extname in ('vector', 'pg_cron');

-- 2. RLS per table. Expect: rls_enabled = true AND rls_forced = true on every row.
select c.relname as table_name, c.relrowsecurity as rls_enabled, c.relforcerowsecurity as rls_forced
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'brain\_%'
order by 1;

-- 3. Policies. Expect: *_read and brain_members_own_row for {authenticated}; *_owner_read,
--    brain_health_owner_all, brain_sync_runs_owner_prune for the owner role only.
--    No policy for anon or public.
select tablename, policyname, roles, cmd, permissive, qual
from pg_policies where schemaname = 'public' and tablename like 'brain\_%'
order by tablename, policyname;

-- 3a. Must return zero rows: a policy that reaches anon or PUBLIC.
select tablename, policyname, roles
from pg_policies
where schemaname = 'public' and tablename like 'brain\_%'
  and (roles @> array['anon']::name[] or roles @> array['public']::name[]);

-- 4. Table privileges per role. Expect: anon all false; authenticated select only (brain_members:
--    column-level select on user_id, scopes, so table-level select shows false); service_role
--    select/insert/update/delete true; truncate false for everyone.
select c.relname as object,
       r.rolname as role,
       has_table_privilege(r.rolname, c.oid, 'select')   as sel,
       has_table_privilege(r.rolname, c.oid, 'insert')   as ins,
       has_table_privilege(r.rolname, c.oid, 'update')   as upd,
       has_table_privilege(r.rolname, c.oid, 'delete')   as del,
       has_table_privilege(r.rolname, c.oid, 'truncate') as trunc
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
cross join (select rolname from pg_roles where rolname in ('anon', 'authenticated', 'service_role')) r
where n.nspname = 'public' and c.relkind in ('r', 'v') and c.relname like 'brain\_%'
order by c.relname, r.rolname;

-- 4a. Column privileges on brain_members for authenticated. Expect: user_id, scopes only.
select column_name, privilege_type, grantee
from information_schema.column_privileges
where table_schema = 'public' and table_name = 'brain_members' and grantee in ('anon', 'authenticated');

-- 4b. Sequence. Expect: anon/authenticated false, service_role true.
select r.rolname, has_sequence_privilege(r.rolname, pg_get_serial_sequence('public.brain_sync_runs', 'id'), 'usage') as usage
from pg_roles r where r.rolname in ('anon', 'authenticated', 'service_role');

-- 5. Functions: definer flag, fixed search_path, execute rights. Expect:
--    brain_current_scopes  definer, search_path="", execute authenticated + service_role
--    brain_search          invoker, search_path="", execute authenticated + service_role
--    brain_refresh_health  invoker, search_path="", execute nobody but the owner
--    anon = false everywhere.
select p.proname,
       p.prosecdef as security_definer,
       p.proconfig as settings,
       has_function_privilege('anon', p.oid, 'execute')          as anon_exec,
       has_function_privilege('authenticated', p.oid, 'execute') as auth_exec,
       has_function_privilege('service_role', p.oid, 'execute')  as service_exec
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.proname like 'brain\_%'
order by 1;

-- 5a. Views run with the caller's rights. Expect: security_invoker=true on every brain_ view (none by default).
select c.relname, c.reloptions
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'v' and c.relname like 'brain\_%';

-- 6. Proof that anon gets nothing. Run this block on its own.
--    Expect: ERROR 42501 "permission denied for table brain_documents" (stronger than zero rows:
--    anon cannot even count). If it returns a number instead, the revoke did not hold: stop.
begin;
set local role anon;
select count(*) as anon_rows from public.brain_documents;
rollback;

-- 6a. Same for the search function. Expect: ERROR 42501 permission denied for function brain_search.
begin;
set local role anon;
select * from public.brain_search(null, null, 'test');
rollback;

-- 7. Proof that a signed-in user with no membership row sees zero rows and has no scopes.
--    Expect: every count 0, scopes {}.
begin;
set local role authenticated;
select set_config('request.jwt.claims',
                  '{"sub":"00000000-0000-0000-0000-00000000dead","role":"authenticated"}', true);
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000dead', true);
select public.brain_current_scopes() as scopes,
       (select count(*) from public.brain_documents)  as documents,
       (select count(*) from public.brain_chunks)     as chunks,
       (select count(*) from public.brain_embeddings) as embeddings,
       (select count(*) from public.brain_records)    as records,
       (select count(*) from public.brain_edges)      as edges,
       (select count(*) from public.brain_sync_runs)  as sync_runs,
       (select count(*) from public.brain_members)    as members,
       (select count(*) from public.brain_ledger('DE')) as ledger_rows,
       (select count(*) from public.brain_search(null, null, 'invoice', 20, array['finance','ops','gtm'])) as search_hits;
rollback;

-- 8. Search as service role on whatever is loaded (zero rows on an empty store is fine;
--    an error is not).
begin;
set local role service_role;
select path, scope, round(score::numeric, 5) as score
from public.brain_search(null, null, 'invoice', 5, array['gtm']);
rollback;

-- 9. Indexes. Expect brain_embeddings_bin_hnsw (hnsw, bit_hamming_ops) and brain_chunks_tsv_gin.
select tablename, indexname, indexdef
from pg_indexes where schemaname = 'public' and tablename like 'brain\_%'
order by tablename, indexname;

-- 10. Other tables in public are untouched. Expect: none of them has a brain policy.
select c.relname,
       (select count(*) from pg_policies p where p.schemaname = 'public' and p.tablename = c.relname
          and p.policyname like 'brain\_%') as brain_policies
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind in ('r', 'p') and c.relname not like 'brain\_%';

-- 11. Owner role. If rolbypassrls is false, the *_owner_read policies are what lets the
--     definer helper and the cron job work; keep them.
select rolname, rolbypassrls, rolsuper from pg_roles
where rolname in (current_user, 'service_role', 'authenticated', 'anon');

-- 12. Any table in public WITHOUT forced RLS, or with RLS off. Expect: zero rows.
select c.relname, c.relrowsecurity, c.relforcerowsecurity
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind in ('r', 'p')
  and (not c.relrowsecurity or not c.relforcerowsecurity);

-- 13. Cron jobs (after 003). Expect three active brain_* jobs owned by the owner role.
select jobname, schedule, username, active from cron.job where jobname like 'brain\_%' order by 1;

-- Also run the project's security advisors (dashboard → Advisors, or get_advisors) and expect
-- no finding on brain_* objects.
