# Time tiers — how the brain stays small without deleting anything

Old material is not removed. It is folded, so that what is current is found first and what is old is one step further away.

| Tier | What | Rule |
|---|---|---|
| **Records** | contracts, invoices, receipts, bank files, journals, meeting folders, client documents | The path never changes once filed. Old ones are hidden by indexes and rollups, not by moving. |
| **Logs and reports** | daily logs, weekly files, audits, finance and marketing reports | Written straight into `<yyyy>/<yyyy-mm>/`. When a month closes it gets a `MONTH.md` rollup; when a year closes, a `YEAR.md`. |
| **Registers** | open loops, deadlines, mail backlog, calendar, routine log | Hold the current month plus everything still open. Older closed blocks move word for word to `00_Brain/ARCHIVE/` by proposal; the owner approves the switch. |
| **Archive** | `_archive/` anywhere, `00_Brain/ARCHIVE/` | Kept, indexed with tier `archive`, left out of default searches (`scripts/brain ask --all` includes it). |

**The ladder:** day → month rollup → year rollup → zip. Month folders older than two years may be zipped beside the year summary after telling the owner. The rollup stays readable; the detail stays recoverable.

**File dating:** the year and month go on the path or at the end of the file name (`_YYYY-MM`). It is the document's date, never the download date.

**Size budgets** are in `tools/vault_health/budgets.json`; `size_check.py` reports what is over.
