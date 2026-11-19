# The index

`.index/vault_index.db` (SQLite, rebuilt from the files at any time; never the source of truth).

| Table | What |
|---|---|
| `files` | one row per file: path, size, hash, kind, area, tier, document date, whether a digest exists |
| `files_fts` | full-text search over names, purposes and text |
| `edges` | links between files (a digest and its original, a summary and its folder) |
| `records` | business records read from the registers: deadline, todo, decision, meeting, client, person, recommendation, ledger_line |
| `runs` | one row per refresh |

- `python3 tools/index/refresh.py` — incremental (daily). `--full` rebuilds (weekly).
- Records are copied **as written**: an amount is a number only when its text is a plain decimal; a date is ISO only when the source writes ISO or dd.mm.yyyy; nothing is converted or summed.
- A record's legal entity comes only from a field that states it (a journal's folder, a register column, a label at the start of a line such as `DE:`), never from free text.
- Each importer in `tools/index/importers/` documents the register shape it reads. Change a register's shape and its importer together.
- Optional: `tools/index/embed/` adds search by meaning (`.index/vectors.db`); `tools/index/supabase_sync.py` copies meaning, never files, to a shared store.
