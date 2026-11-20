# Weekly run — week ahead, finance week, catch-up of the weekday blocks

**Status:** active · **Cadence:** Monday morning · **Version:** 2

Rules: the root `AGENTS.md` (binding) and `00_Brain/SYSTEM/TIME_TIERS.md`. Read the last seven daily entries of `00_Brain/SCHEDULES/ROUTINE_LOG.md` first.

This run tells the owner what the week demands, closes the finance week and makes sure no weekday block was lost. The cleanup, the audit, the dream and the improvement proposals are the daily run's work, one block per weekday (`daily.md` Step 3b); they are described there and nowhere else.

## The to-do for this run (it is finished when all seven are ticked)

- [ ] 1. **Week and month ahead written first:** deadlines for 7 and 30 days, money to pay, money to collect, every draft invoice with why it was not sent, promises to clients, at most five decisions for the owner.
- [ ] 2. Finance week closed per legal entity: receivables, payables, missing receipts, journal lines without a document, the separation check.
- [ ] 3. First Monday of a month: the month closed per entity.
- [ ] 4. **The six weekday blocks read from the routine log:** each finished block's result read into Part A; every block that is `partly` or `not run` done now by its own checklist; the dream never skipped; open items of `00_Brain/SYSTEM/BRAIN_TODO.md` older than two weeks named.
- [ ] 5. The syncs done and reported, plus the backup copy of the store and the age of the last backup.
- [ ] 6. The other brains' weekly routines run or reported.
- [ ] 7. The weekly file, Monday's `TODO.md` (led by Part A, "The brain suggests" kept) and the routine-log entry written; the final message sent.

**Order:** write Part A first, so it exists even if a later part fails. Part B and a block that has to be caught up may go to helpers, at most two at a time; each gets one area, does the work itself and returns its report as text.

## Step 0 — skeleton and preflight

Create `00_Brain/WEEKLY/<yyyy>/<yyyy-mm>/<yyyy>-W<ww>.md` (the month that holds the week's Thursday) with the headings of parts A to E. Run the same preflight as the daily run and write the table into the file.

## Part A — the week and the month ahead (the owner reads this first)

1. **Deadlines in the next 7 and 30 days**, per legal entity: authority dates, tax returns, licence and contract renewals, insurance, adviser appointments. Ranked by the cost of a miss; each CONFIRMED or NEEDS VERIFICATION.
2. **Money to pay** in the next 7 and 30 days per entity, against the cash that is there (an unknown balance stays unknown).
3. **Money to collect:** open and overdue invoices per entity, **every invoice still in draft and why it was not sent**, and work that can be invoiced now.
4. **Promises to clients** due this week and replies we owe that are older than three days.
5. **Decisions waiting for the owner**, at most five, each with the options and a recommended default: from `00_Brain/OPEN_POINTS.md` and `00_Brain/RECOMMENDATIONS.md`. Close a point only when a document, a ledger entry or the owner's written answer settles it; then move it word for word to `00_Brain/ARCHIVE/OPEN_POINTS_closed.md`.

Also in Part A, two lines each: the pipeline (`03_Sales/PIPELINE_NOW.md` brought up to date from the week's mail and meetings, by `.claude/skills/sales-pipeline/SKILL.md`) and what marketing published or has ready (`.claude/skills/marketing/SKILL.md`).

## Part B — finance week (one legal entity at a time)

6. `python3 tools/index/importers/run_all.py --db .index/vault_index.db --check`: read the journal checks (rows without an amount, a currency or a source document; entries that do not balance).
7. Per entity: receivables, payables, receipts missing for booked costs, differences between the invoicing tool, the bookkeeping tool and the journal, bills filed under the wrong entity.
8. **First Monday of a month: month close.** Per entity: the month's journal complete, the receipts gap listed, the tax return prepared for the person who files it, one monthly report in `finance/reports/<yyyy>/<yyyy-mm>/`.

## Part C — the weekday blocks: read the results, catch up what did not finish

Fewer schedules, each with real to-do items. The daily run does one block of work on the brain each day, and the procedure of every block lives in one place, `daily.md` Step 3b (Monday apply, Tuesday evaluate, Wednesday enrich, Thursday clean up, Friday audit, Saturday dream, Sunday improve). This run does none of that work a second time.

9. Read the last seven routine-log entries (their `block:` lines) and `00_Brain/SYSTEM/BRAIN_TODO.md`, and fill this table into the weekly file. The week meant here is the one that ended yesterday.

| Block | Day | State in the routine log | Result file |
|---|---|---|---|
| Evaluate | Tuesday | | `00_Brain/SYSTEM/EVALUATIONS/<yyyy>-W<ww>.md` |
| Enrich | Wednesday | | the daily log |
| Clean up | Thursday | | the daily log, `00_Brain/ARCHIVE/_proposed/` |
| Audit | Friday | | `00_Brain/AUDITS/<yyyy>/<yyyy-mm>/` |
| Dream | Saturday | | `00_Brain/SYSTEM/DREAMS/<yyyy>-W<ww>.md` |
| Improve | Sunday | | `00_Brain/SYSTEM/IMPROVEMENTS.md` |

10. **Catch-up rule.** A block that ended `done` is not repeated; only read its result into Part A (rollovers waiting for a yes and audit findings that need the owner go under item 5). A block that is `partly` or `not run` is done now, by that block's checklist in `daily.md` Step 3b, and its result is written where that block writes it. The dream is never skipped: if last week has no dream file, write it today and put its three strongest entries on Monday's page. On the first Monday of a month make sure the month rollups of Thursday's block exist; if not, write them now. Name every open item of `BRAIN_TODO.md` that is older than two weeks. This run applies nothing: Monday evening's daily block applies what the owner answered.

## Part D — the syncs and the backup

11. `python3 tools/index/refresh.py --full` → if you run a shared store: `python3 tools/index/supabase_sync.py --apply` → `--verify` → `--backup` (the store pulled back into a local SQLite file). Report the counts and the verify line.
12. Backup: say how old the newest backup of this folder is. Older than seven days: put "run the backup" on the owner's page.

## Part E — the other brains' weekly routines

13. This run is their scheduler. For each linked brain whose `schedules/weekly.md` exists, read it, run it inside that repository, append to its routine log, and report five lines. Commit and push nothing.

## Write and finish

- The weekly file with parts A to E, each item with its state and findings.
- Root `TODO.md`: Monday's page, led by Part A. Before rewriting it, copy the owner's answers on it to `00_Brain/SYSTEM/IMPROVEMENTS.md` (the same rule as `daily.md` Step 3), and keep the section "The brain suggests" that Sunday's block wrote; an entry leaves it only when the owner has answered.
- One appended entry in `00_Brain/SCHEDULES/ROUTINE_LOG.md`, with the block table in one line.
- Final message, short: the week ahead in seven lines · money to pay and to collect per entity · drafts not sent · decisions waiting · the six blocks (done, caught up today, still open) · audit findings that need the owner · the sync and backup results · the dream's three strongest entries · improvement proposals waiting for a yes · anything skipped and why.

## Rules that decide doubtful cases

Unknown stays `unknown`. Legal entities never share a line, a sum or a currency column. No personal identifiers or access codes in any file. Never delete. You draft; the owner sends, pays and files. Rule and schedule changes are proposed, never applied without the owner's yes.
