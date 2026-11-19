# The shared store (optional)

A team that should search the same knowledge without sharing one laptop can copy meaning into a Postgres database (the schema is written for Supabase with the `vector` and `pg_cron` extensions). **Files never go up**: only text chunks from text files and digests, their embeddings, and business records.

As pictures: `docs/DIAGRAMS.md`, diagrams 17 (what may leave the computer) and 18 (reading the store).

## What protects it

- **Scopes.** Every row has one: `finance`, `ops`, `gtm`, `outreach`, `templates`, `design`, or `client:<slug>`. A signed-in user sees only rows whose scope is in their membership row.
- **Row-level security on every table, forced**, and nothing at all for anonymous access.
- **One file decides what leaves the computer:** `tools/index/supabase/scopes.json`. A never list (paths, name patterns, guarded client folders, text terms) is checked before anything else.
- **Private scopes are off until the owner confirms in writing who can open the database's dashboard.** Anyone with dashboard access bypasses row-level security. While `owner_confirmed_private_scopes` is false, `finance`, `ops` and client scopes are refused whatever the command line says.
- **A client scope goes up only if its slug is listed**, and never for a client that is confidential or sends special-category data.
- **Redaction before upload**, the same as before embedding.
- **A ledger can only be read one legal entity at a time** (`brain_ledger('<CODE>')`).

## Set up

1. Create a project; enable `vector` and `pg_cron`.
2. Copy `.env.example` to `.env` and fill it. Never commit `.env`.
3. Apply `tools/index/supabase/001_brain_store.sql`, then `003_cron.sql`, then run `002_checks.sql` block by block and read every result (blocks 6 and 6a are meant to fail with a permission error, so run each alone; check 12 lists every table in `public` without forced row-level security, including tables of yours that have nothing to do with the brain). The checks prove that anonymous access gets a permission error and that a user without a membership sees zero rows. **Do not load data until they pass.**
4. `python3 tools/index/supabase_sync.py --plan` shows what would go up, by scope, and what the never list blocked. Read it.
5. `--apply`, then `--verify` (counts on both sides must match), then `--backup` to pull the store back into a local SQLite file.

The SQL in this template was generalised from a working setup by replacing fixed company codes with configurable ones, and has not been run in this form. Treat it as reviewed-by-you code: read it and run the checks before trusting it with anything private.

`--walk <folder> --scope <scope>` sends that folder's text to that scope whatever the routing rules say; only the never list and a brain's own `brain/DATA_HANDLING.md` stop it. Use it only on a repository that is meant for that team.

## What we would tell a friend

A shared store is a second place your company's knowledge lives. Start with the non-sensitive scopes (`gtm`, `templates`, `design`). Add finance only if someone other than you truly needs to search it, and they usually do not.
