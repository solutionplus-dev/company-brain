---
name: vault-audit
description: Audit the brain for inconsistencies — registers against folders, legal entities kept apart, identifiers or secrets in text files, dead links, logs out of their month folders, missing routine-log entries. Read-only. Use for Friday's block of the daily run (daily.md Step 3b), for the weekly run when it catches that block up, or "audit the brain", "is anything inconsistent".
---

# Audit

Findings only; an audit changes nothing.

1. `CLIENTS.json` against `01_Clients/` folders; `registry.json` against `02_Meetings/` folders.
2. Legal entities: a journal, report or table that holds two; a document filed under the wrong entity.
3. Identifiers and secrets in text files: ID numbers, dates of birth, private addresses, account numbers, keys, tokens, login links. Report the path and the kind, never the value.
4. Links in summaries and registers that point to nothing.
5. Logs outside `<yyyy>/<yyyy-mm>/`; closed months without a rollup.
6. A routine-log entry for every day of the week; sources "not read" three days running.
7. The same fact in two files with different values (`00_Brain/SYSTEM/SYSTEM_OF_RECORDS.md` names the owner).
8. `python3 tools/vault_health/size_check.py` for registers over budget.

Write `00_Brain/AUDITS/<yyyy>/<yyyy-mm>/<date>_audit.md`: finding, path, why it matters, suggested fix.
