# Weekly run — week ahead, finance week, cleanup and compaction, the dream, self-improvement

**Status:** active · **Cadence:** Monday morning · **Version:** 1

Rules: the root `AGENTS.md` (binding) and `00_Brain/SYSTEM/TIME_TIERS.md`. Read the last seven daily entries of `00_Brain/SCHEDULES/ROUTINE_LOG.md` first.

## The to-do for this run (it is finished when all ten are ticked)

- [ ] 1. **Week and month ahead written first:** deadlines for 7 and 30 days, money to pay, money to collect, every draft invoice with why it was not sent, promises to clients, at most five decisions for the owner.
- [ ] 2. Finance week closed per legal entity: receivables, payables, missing receipts, journal lines without a document, the separation check.
- [ ] 3. First Monday of a month: the month closed per entity.
- [ ] 4. The closed month folded: rollups written, logs in their month folders; in January the year rollup.
- [ ] 5. Registers checked for size; rollovers prepared for the owner's yes; loose files filed or listed; summaries trimmed with history kept.
- [ ] 6. The brain audited; stale notes listed and the three most important refreshed; facts stated twice with different values listed.
- [ ] 7. Linked brains and repositories re-checked (rules, routines, index, unpushed work).
- [ ] 8. The syncs done and reported, plus the backup copy of the store and the age of the last backup.
- [ ] 9. The other brains' weekly routines run or reported.
- [ ] 10. **The dream written** (five buckets, its three strongest entries on Monday's page) and improvement proposals listed for the owner's yes; the weekly file, Monday's `TODO.md` and the routine-log entry written; the final message sent.

Boxes 4, 5, 6, 7 and 10 are ticked by the weekday block's own result when the routine log shows it ended `done` (see the next section); otherwise this run does that part now.

**Order:** write Part A first, so it exists even if a later part fails. Parts B, C and D may go to helpers, at most two at a time; each gets one area, does the work itself and returns its report as text.

## The weekday blocks, and what Monday does about them

Fewer schedules, each with real to-do items. The upkeep, the audit, the dream and the improvement proposals no longer wait for Monday: the daily run does one block each day (`daily.md` Step 3b: Monday apply, Tuesday evaluate, Wednesday enrich, Thursday clean up, Friday audit, Saturday dream, Sunday improve). Parts C, D, G and H below remain the procedure for those blocks.

On Monday this run reads the last seven routine-log entries first and fills this table into the weekly file:

| Block | Day | State in the routine log | Result file |
|---|---|---|---|
| Evaluate | Tuesday | | `00_Brain/SYSTEM/EVALUATIONS/<yyyy>-W<ww>.md` |
| Enrich | Wednesday | | the daily log |
| Clean up | Thursday | | the daily log, `00_Brain/ARCHIVE/_proposed/` |
| Audit | Friday | | `00_Brain/AUDITS/<yyyy>/<yyyy-mm>/` |
| Dream | Saturday | | `00_Brain/SYSTEM/DREAMS/<yyyy>-W<ww>.md` |
| Improve | Sunday | | `00_Brain/SYSTEM/IMPROVEMENTS.md` |

**Catch-up rule:** a block that ended `done` is not repeated; this run only reads its result into Part A. A block that is `partly` or `not run` is done now, by its part below (C for clean up, D for audit, G for the dream, H for improve; evaluate and enrich by `daily.md` Step 3b). The dream is never skipped: if Saturday's did not happen, Part G runs today. Monday evening's daily run then applies what the owner answered.

## Step 0 — skeleton and preflight

Create `00_Brain/WEEKLY/<yyyy>/<yyyy-mm>/<yyyy>-W<ww>.md` (the month that holds the week's Thursday) with the headings of parts A to H. Run the same preflight as the daily run and write the table into the file.

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

## Part C — cleanup and compaction

Records never move; logs and reports are tiered; registers roll over. Nothing is deleted; every move is `mv -n` and written to a move list in `00_Brain/SYSTEM/moves/`.

9. **Close the last month if a new one began.** For daily logs, weekly files, audits, finance reports, marketing reports and meetings: write the month rollup (`MONTH.md`: what happened, decisions, money with certainty, what is still open) and make sure that month's files sit in `<yyyy>/<yyyy-mm>/`. In January: `YEAR.md` for the closed year. Month folders older than two years may be zipped beside the year summary, after telling the owner.
10. **Registers.** `python3 tools/vault_health/size_check.py`; for each register over budget prepare the rollover (`python3 tools/vault_health/rollover.py stage <path>`). Switching a live register to its rolled-over version needs the owner's yes: list the prepared ones under Part A item 5.
11. **Loose files.** The root, `00_Brain/INBOX/`, client folder roots, the downloads folder older than seven days: file what is identifiable (copy, never move out of downloads), list what is not. Duplicates and stray temporary files are listed with sizes and the exact command for the owner, never removed.
12. **Summaries and client files.** Every folder changed during the week has a `SUMMARY.md` with today's "Last verified"; older history goes word for word to `SUMMARY_HISTORY.md`. A client `STATUS.md` whose "Now" area passed about 25 lines: oldest blocks to `STATUS_HISTORY.md`.

## Part D — the brain checks itself (read only)

13. **Audit:** registries against folders; legal entities kept apart; identifiers, access codes or secrets in text files; dead links; logs in their month tiers; a routine-log entry for every day of the week; diagrams in `docs/DIAGRAMS.md` that name a step, a file or an order a routine no longer has. Write `00_Brain/AUDITS/<yyyy>/<yyyy-mm>/<date>_audit.md`.
14. **Refresh sweep.** Every note whose `refresh_by` has passed or whose "Last verified" is older than 60 days: regenerate the three most important from their sources and re-stamp them; list the rest.
15. **One home per fact.** Against `00_Brain/SYSTEM/SYSTEM_OF_RECORDS.md`: where the same fact is stated in two files with different values, name both and the owning file; add what cannot be settled to `00_Brain/OPEN_POINTS.md`.
16. **Linked brains and repositories** under `Repos/`: rule file present, routine files present, work not pushed, pull requests open. Report; change nothing there.

## Part E — the syncs and the backup

17. `python3 tools/index/refresh.py --full` → if you run a shared store: `python3 tools/index/supabase_sync.py --apply` → `--verify` → `--backup` (the store pulled back into a local SQLite file). Report the counts and the verify line.
18. Backup: say how old the newest backup of this folder is. Older than seven days: put "run the backup" on the owner's page.

## Part F — the other brains' weekly routines

This run is their scheduler. For each linked brain whose `schedules/weekly.md` exists, read it, run it inside that repository, append to its routine log, and report five lines. Commit and push nothing.

## Part G — the dream (once a week; read everything, propose, apply nothing)

The dream is the brain thinking about the company while nobody is asking. It reads the whole week and comes back with proposals the owner can accept, refine or dismiss. It never changes a rule, a schedule, a register or a record.

19. **Read the week:** the seven daily logs and their answer sheets, the routine log, the week's meetings, what changed in `OPEN_POINTS.md` and `RECOMMENDATIONS.md`, the money movements per entity, the client `STATUS.md` "Now" blocks, and every correction the owner made to the brain's output.
20. **Write `00_Brain/SYSTEM/DREAMS/<yyyy>-W<ww>.md`** with at most three entries in each of five buckets, every entry with its evidence (paths) and the exact change it proposes:
    1. **Notice** — a pattern across days that no single run reported (a client going quiet, a cost creeping, the same question asked twice, a promise slipping).
    2. **Knowledge** — a fact worth a topic note, or a note that the week's evidence made wrong.
    3. **Rules** — a rule two runs applied differently, a rule the owner overrode, a missing rule.
    4. **Routines** — a checklist item to add, merge or drop; a source to reconnect; a new routine as a file in `00_Brain/SCHEDULES/proposed/`.
    5. **For the owner** — an opportunity or a risk with a recommended next step (never a tax or legal conclusion: a question for the adviser instead).
21. **Morning suggestion:** the three strongest entries go to the top of Monday's `TODO.md` under "The brain suggests", each answerable with `yes`, `no` or a correction.

## Part H — self-improvement (apply only what carries a yes)

22. Carry the dream's Rules and Routines entries, and anything below, into `00_Brain/SYSTEM/IMPROVEMENTS.md` as proposals, each with the evidence and the exact change:
    - a source that was "not read" on three or more days: what to reconnect or replace;
    - a checklist item that was "nothing" for four weeks: drop, merge or look somewhere else;
    - something the owner had to ask for by hand that an item should have caught: the new item;
    - a rule that two runs applied differently: the clearer wording.

    The owner answers `yes`, `no` or a correction on the line. This run applies nothing: Monday evening's daily block (`daily.md` Step 3b, Apply) applies what carries a yes.

## Write and finish

- The weekly file with parts A to H, each item with its state and findings.
- Root `TODO.md`: Monday's page, led by Part A. Before rewriting it, copy the owner's answers on it to `00_Brain/SYSTEM/IMPROVEMENTS.md` (the same rule as `daily.md` Step 3).
- One appended entry in `00_Brain/SCHEDULES/ROUTINE_LOG.md`.
- Final message, short: the week ahead in seven lines · money to pay and to collect per entity · drafts not sent · decisions waiting · what was folded and archived (counts) · audit findings that need the owner · the sync and backup results · the dream's three strongest entries · improvement proposals waiting for a yes · anything skipped and why.

## Rules that decide doubtful cases

Unknown stays `unknown`. Legal entities never share a line, a sum or a currency column. No personal identifiers or access codes in any file. Never delete. You draft; the owner sends, pays and files. Rule and schedule changes are proposed, never applied without the owner's yes.
