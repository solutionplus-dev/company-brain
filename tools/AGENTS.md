# tools — rules for agents working on the brain's own code

Read the root `AGENTS.md` first.

- `index/` — catalogue, records, search (`refresh.py`, `query.py`, `importers/`); optional embeddings (`embed/`); optional shared store (`supabase/`, `supabase_sync.py`). Standard library only, except the embedding lane, which has its own virtual environment.
- `vault_health/` — `size_check.py` (budgets, read-only), `rollover.py` (stages register rollovers as proposals; never writes a live register).

1. **The index is rebuilt from the files, never the other way round.** No tool writes a register, a record or a journal.
2. **Nothing about the company is hard-coded.** Names and legal entities come from `brain.config.json` through `index/brainconfig.py`.
3. **A register's shape and its importer change together.** Run `python3 tests/test_smoke.py` after either.
4. **What may leave the computer is decided in one file:** `index/supabase/scopes.json`. When in doubt, a path stays local.
5. **No secret in code or in a log.** Keys are read from `.env` by name and never printed.
