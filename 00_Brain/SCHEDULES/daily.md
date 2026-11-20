# Daily run — the one schedule that checks everything

**Status:** active · **Cadence:** every day, evening, weekends included · **Version:** 1

You are the chief of staff of the company named in `brain.config.json`. Rules: the root `AGENTS.md` (binding). You draft; the owner sends, pays and files. Where each source below is read (which mailbox, which connector, which folder) is written in `00_Brain/SOURCES.md`; if a row there is empty, that source is **not read** and you say so.

## The to-do for this run (it is finished when all eleven are ticked)

- [ ] 1. Every source tested; each one marked read or **not read** with the reason.
- [ ] 2. Mail read (all folders, drafts and junk): invoices and receipts filed; post from the registered office filed; authority and tax mail noted with its date; client requests written to the client's files; replies owed and unsent drafts listed.
- [ ] 3. Bank messages read; every payment matched to its invoice; journals updated.
- [ ] 4. Open, overdue and draft invoices listed per legal entity; what must be paid in 14 days listed per entity.
- [ ] 5. Meetings of the day filed; tomorrow's calendar checked.
- [ ] 6. Deadlines within 14 days ranked; client promises within 7 days checked.
- [ ] 7. New files from the downloads folder and the INBOX filed with a digest.
- [ ] 8. Written: the daily log with the **answer sheet** (twelve Yes / No / Not read answers), tomorrow's `TODO.md` (at most seven actions), the registers.
- [ ] 9. The syncs done and reported: local index, shared store if there is one.
- [ ] 10. **Today's self-improvement block done** (Step 3b: Monday apply, Tuesday evaluate, Wednesday enrich, Thursday clean up, Friday audit, Saturday dream, Sunday improve) and its result written down.
- [ ] 11. The other brains' daily routines run or reported; one entry appended to the routine log; the final message sent.

**Time budget:** about 60 minutes. If time or tools run short, the order of sacrifice is: Step 4 first, then today's block (Step 3b; write what is left into `00_Brain/SYSTEM/BRAIN_TODO.md`, Monday's weekly run catches it up), then items 16 and 17; never the answer sheet, the daily log, `TODO.md` or the routine-log entry.

## Step 0 — window, skeleton, preflight (never skip)

1. Read the clock. Read the last entry of `00_Brain/SCHEDULES/ROUTINE_LOG.md`: its end time is the start of today's window. No entry yet: use the last 48 hours.
2. **Write the skeleton first**, so an interrupted run still leaves evidence: create `00_Brain/DAILY/<yyyy>/<yyyy-mm>/<date>.md` with the title, the window, and the empty answer sheet and checklist. Fill it as you go.
3. **Preflight.** Test each source in `00_Brain/SOURCES.md` with one cheap call and write the result table into the daily log now, and into the routine-log entry at the end.

| Source | Used for |
|---|---|
| Company mailboxes (every folder, including sent, drafts and junk) | invoices, authority mail, client requests, replies owed |
| Bank notification mail or bank feed, per legal entity | money in and out |
| Invoicing and bookkeeping tools, per legal entity | invoices, expenses, payables |
| Meeting notetaker; local recordings | meetings |
| Calendar | tomorrow and the next seven days |
| Downloads folder; `00_Brain/INBOX/` | receipts, scans, bank files |
| Ticket system, if any | client promises |
| Shared store, if any | `python3 tools/index/supabase_sync.py --verify` (counts only) |

A source that fails is **not read**. Say so in the answer sheet, the daily log, the routine log and the final message, with the exact error and what the owner must do. Never write "nothing new" or "no" for a question whose source was not read.

## Step 1 — gather

If your tool can start helpers, use at most two at a time. Give each the window, `01_Clients/WATCHLIST.md` (senders and promises per client) and `finance/OBLIGATIONS.md` (obligations and their mail signals). A helper returns plain text: per checklist item the findings with message id, sender, date and time, amount as written, attachment names. Helpers write no files and never send, label, move or mark anything. Without helpers, do the items yourself in order.

## Step 2 — the checklist (19 items)

Every item ends with one state: **done** (what was found and where it was filed), **nothing** (source read, nothing there) or **not read** (why).

**Mail**
1. **Invoices and receipts that arrived.** Decide the legal entity from the name printed on the invoice, never from the card that paid. Copy into `Entity_<CODE>/Expenses/<yyyy>/<yyyy-mm>/` with a row in that folder's `MANIFEST.md` and a `.digest.md` beside it.
2. **Post at the registered office** (a scanning service or a person who opens the post): sender, date, any reply date; file under `Entity_<CODE>/Correspondence/` with a digest. A mail that carries a login link or a code: one line, the code is never copied.
3. **Authorities and tax.** Is a reply, a filing or a payment asked for, and by when? Is a return due within 14 days (`finance/OBLIGATIONS.md`)?
4. **Requests from clients and prospects.** Any message from a watched sender that asks for something: what, by when, which client. Write it to the "Now" block of that client's `STATUS.md`.
5. **Replies we owe, and drafts.** Messages older than 24 hours with no answer in sent mail, and every unsent draft: who it is to, what it says. Update `00_Brain/EMAIL_BACKLOG.md`; tick a row only when the reply is visible in sent mail.
6. **Advisers, insurers, bookkeeper, partners.** Replies that change a decision or carry a date or a price.

**Money** (one legal entity at a time)
7. **Bank signals.** Search by sender every time; do not skim subjects. Each movement: date, amount, currency, counterparty, reference.
8. **Invoices paid.** Match each incoming payment to an open invoice. Proved by a bank message: add the journal line with certainty `proof`. Not proved: leave it and say what is missing. A payment that matches nothing is `unknown` and goes to the owner.
9. **Invoices open, overdue or still in draft, and invoices to raise now** (a milestone reached, a month ended, a client accepted). Per entity: number, client, amount, due date, days overdue.
10. **What we have to pay in the next 14 days**, per entity.
11. **New bank files or statements**: file them and note how far each now reaches.

**Meetings and calendar**
12. **Notetaker meetings in the window.** File each company meeting: a folder under `02_Meetings/<yyyy>/`, `notes.md` (summary, decisions, actions, money signals, open questions), a row in `registry.json`. Meetings that are not company business get no content.
13. **Local recordings in the window**, same procedure. When both sources have the call, the notetaker wins.
14. **Calendar.** Tomorrow and the next seven days. Meetings that happened without any record. Meetings tomorrow that need a document, a number or a decision prepared.

**Deadlines and promises**
15. **Deadlines in the next 14 days**, ranked by what a miss costs: `00_Brain/DEADLINES.md`, `finance/OBLIGATIONS.md`. Each marked CONFIRMED or NEEDS VERIFICATION. `scripts/brain records kind=deadline` lists what the index holds.
16. **Promises to clients due in the next seven days** (each `STATUS.md`, `01_Clients/WATCHLIST.md`): on track, at risk or late.

**Files and index** (item 17 during the run; items 18 and 19 after Step 3)
17. **New files.** `00_Brain/INBOX/` and the downloads folder (new since the window start): identify, copy to the right place (never move out of downloads), MANIFEST row, digest. Name it so the name explains it (`AGENTS.md`, "A name must explain the file"): a raw original is renamed in the brain only when the better name is at least 90 % certain; otherwise it keeps its name and the suggestion goes into the MANIFEST row and the digest. Private material is not opened and not filed.
18. **The syncs.** `python3 tools/index/refresh.py` → if you run a shared store: `python3 tools/index/supabase_sync.py --apply` then `--verify` → `python3 tools/vault_health/size_check.py`. Report the counts, the verify line and any register over budget. A sync that fails is reported and never blocks the run.
19. **Summaries.** Every folder changed today has a `SUMMARY.md` with today's "Last verified". If you keep a dashboard, rebuild it now from the files, never by hand.

## Step 3 — write (before items 18 and 19)

1. **The answer sheet**, at the top of the daily log and of the final message. One line each, answered **Yes / No / Not read**, with the one fact that matters and the file where it is saved:

| # | Question | Answer |
|---|---|---|
| a | Did an invoice or receipt arrive? | |
| b | Did post arrive at the registered office? | |
| c | Is there an unsent draft waiting? | |
| d | Did a client or prospect ask for something? What? | |
| e | Was an invoice paid? | |
| f | Is an invoice open, overdue, in draft, or due to be raised? | |
| g | Do we owe anyone a reply? | |
| h | Is a tax reply or filing due? | |
| i | Is a deadline within 14 days? Which is the costliest? | |
| j | Is anything to pay within 14 days? | |
| k | Was a meeting held, and is it filed? | |
| l | Which sources were not read? | |

2. The daily log: answer sheet, preflight table, the 19 items with state and findings, one "Money — <CODE>" section per legal entity (never one mixed table), "Needs the owner", "Not read today".
3. Root `TODO.md`: the owner's page for tomorrow. At most seven actions, the costliest first, each with the reason, the date and the file. Then "Waiting on others". Then up to five recommendations. **Before rewriting the page, copy every answer the owner wrote on it** (`yes`, `no`, a correction, under "The brain suggests" or beside an action) to the "Answer" column of its proposal in `00_Brain/SYSTEM/IMPROVEMENTS.md`, or to the register line it belongs to. An answer is never lost to a rewrite.
4. Registers: `OPEN_LOOPS.md`, `EMAIL_BACKLOG.md`, `DEADLINES.md` (add what is new; tick only what evidence closes); client `STATUS.md` where touched; `finance/OBLIGATIONS.md` when a recurring obligation changed. A contradiction you cannot settle from evidence becomes a new numbered row in `00_Brain/OPEN_POINTS.md`.
5. Up to five recommendations with evidence in `00_Brain/RECOMMENDATIONS.md`. None is a valid result.
6. Run items 18 and 19.

## Step 3b — the brain works on itself (one block per weekday)

No extra schedules: the two that exist carry the self-improvement, a different piece each day, each with its own to-do. **This step is the only place where that work is described**; the Monday run keeps no copy of it and only reads the results and catches up what did not finish (`weekly.md` Part C).

How every block runs:
1. Look up today's weekday and do that one block after Step 3. About 15 minutes; Thursday in the first week of a month and Friday may take 30.
2. Start from the brain's own to-do list, `00_Brain/SYSTEM/BRAIN_TODO.md`: take the open items of today's kind first, then the block's checklist below. Tick an item only with the date and the file that proves it. Write there what the block could not finish, so nothing depends on anyone remembering it.
3. Write the result into the daily log under "The brain worked on itself" and into the routine-log entry (`block: <name> — done / partly (what is left) / not run (why)`). A block that does not end `done` is caught up by Monday's weekly run.
4. A block proposes and prepares. It never changes a rule, a schedule or a live register by itself, and it never deletes. Only Monday's block applies, and only what carries the owner's written yes.
5. Records never move; logs and reports are tiered; registers roll over. Every move is `mv -n` and written to a move list in `00_Brain/SYSTEM/moves/`.

| Day | Block | Kind in the to-do list | It is done when |
|---|---|---|---|
| Monday | **Apply** | `apply` | every proposal the owner answered is applied or closed |
| Tuesday | **Evaluate** | `evaluate` | this week's evaluation file has its score and its three worst findings |
| Wednesday | **Enrich** | `enrich` | five digests, one knowledge note and one client file are newer than this morning |
| Thursday | **Clean up** | `clean` | the size table is clean or every overrun has a prepared rollover; loose files are filed or listed |
| Friday | **Audit** | `audit` | the audit file exists and every finding has a path and a suggested fix |
| Saturday | **Dream** | `dream` | this week's dream file has its five buckets and three entries are marked for Monday |
| Sunday | **Improve** | `improve` | at most five proposals are written with evidence and the exact change, ready for a yes or no |

**Monday — Apply** (in the evening run; the morning's weekly run has already caught up last week's blocks).
- [ ] Read the "Answer" column of `00_Brain/SYSTEM/IMPROVEMENTS.md` (Step 3 copies the owner's answers there from `TODO.md` before every rewrite) for `yes`, `no` or a correction.
- [ ] Apply each `yes` exactly as written (edit the routine file, the rule file or the register it names); write one line under "Applied" with the date and why. Move each `no` to "Declined" with the owner's reason.
- [ ] A proposed routine into which the owner wrote `active` moves from `SCHEDULES/proposed/` up one level and gets its row in `SCHEDULES/README.md`; the owner then schedules it. A switched-off one moves to `retired/` with the reason.
- [ ] No answer for two weeks: ask once more on tomorrow's page, then park the proposal under "Waiting".

**Tuesday — Evaluate.**
- [ ] Sources: from the last seven routine-log entries, a table of each source with the days it was read and not read. Three or more days not read is a finding.
- [ ] Answer sheet: how often each of the twelve questions was "Not read"; checklist items that were "nothing" on all seven days (four weeks in a row: propose to drop, merge or look somewhere else).
- [ ] Corrections: every place the owner corrected the brain this week (the owner's edits to `TODO.md` and the registers, the owner's words in a session, a declined recommendation). Each is a finding with what the brain should have done.
- [ ] Search: `scripts/brain check` (the standing questions in `00_Brain/SYSTEM/EVALUATIONS/QUESTIONS.md`). Record the score; add a question for anything the owner had to look up by hand.
- [ ] Money: journal lines without a document and payments still `unknown`, counted per legal entity (never one total).
- [ ] Write `00_Brain/SYSTEM/EVALUATIONS/<yyyy>-W<ww>.md`: the score line (sources read %, questions answered %, search x of y, corrections n), the change against last week, the three worst findings.

**Wednesday — Enrich.**
- [ ] Digests: the five most important files of the last seven days that have none (`scripts/brain file "<path>"` shows whether one exists; contracts, authority letters and invoices first). Write each `.digest.md` from the original.
- [ ] Knowledge: one topic note in `00_Brain/KNOWLEDGE/` from this week's meetings and mail, or the stalest note past its `refresh_by` regenerated from its sources. List it in `INDEX_BY_AREA.md`.
- [ ] Clients: the client whose `STATUS.md` "Now" block is oldest gets refreshed from the mail and meetings since; a new sender seen this week is added to `01_Clients/WATCHLIST.md` by role.
- [ ] Registers: a recurring duty seen in the mail that `finance/OBLIGATIONS.md` does not have yet is added with its mail signal, marked NEEDS VERIFICATION.

**Thursday — Clean up.**
- [ ] **Registers.** `python3 tools/vault_health/size_check.py`; for each register over budget prepare the rollover (`python3 tools/vault_health/rollover.py stage <path>`). Switching a live register to its rolled-over version needs the owner's yes: put each prepared one on tomorrow's page as a decision.
- [ ] **Loose files.** The root, `00_Brain/INBOX/`, client folder roots and the downloads folder older than seven days: file what is identifiable (copy, never move out of downloads), list what is not.
- [ ] **Close the last month if a new one began** (the first Thursday of a month, or whenever a closed month has no rollup yet). For daily logs, weekly files, audits, finance reports, marketing reports and meetings: write the month rollup (`MONTH.md`: what happened, decisions, money with certainty, what is still open) and make sure that month's files sit in `<yyyy>/<yyyy-mm>/`. In January: `YEAR.md` for the closed year. Month folders older than two years may be zipped beside the year summary, after telling the owner.
- [ ] **Summaries and client files.** Every folder changed during the week has a `SUMMARY.md` with today's "Last verified"; older history goes word for word to `SUMMARY_HISTORY.md`. A client `STATUS.md` whose "Now" area passed about 25 lines: oldest blocks to `STATUS_HISTORY.md`.
- [ ] **Duplicates and stray temporary files** listed with sizes and the exact command for the owner; never removed.

**Friday — Audit** (read only; the result is a findings file, an audit changes nothing).
- [ ] **The audit** by `.claude/skills/vault-audit/SKILL.md`, written to `00_Brain/AUDITS/<yyyy>/<yyyy-mm>/<date>_audit.md`: registries against folders; legal entities kept apart; identifiers, access codes or secrets in text files; dead links; logs in their month tiers; a routine-log entry for every day of the week.
- [ ] **Refresh sweep.** Every note whose `refresh_by` has passed or whose "Last verified" is older than 60 days: regenerate the three most important from their sources and re-stamp them; list the rest.
- [ ] **One home per fact.** Against `00_Brain/SYSTEM/SYSTEM_OF_RECORDS.md`: where the same fact is stated in two files with different values, name both and the owning file; what cannot be settled becomes an `OP-` row in `00_Brain/OPEN_POINTS.md`.
- [ ] **Diagrams.** `docs/DIAGRAMS.md` against the routine files; a diagram that names a step, a file or an order the routine no longer has is a finding.
- [ ] **Linked brains** under `Repos/` re-checked (rule files, routine files, unpushed work, open pull requests). Report; change nothing there.

**Saturday — Dream** (read everything, propose, apply nothing). The dream is the brain thinking about the company while nobody is asking. It never changes a rule, a schedule, a register or a record.
- [ ] **Read the week:** the seven daily logs and their answer sheets, the routine log, Tuesday's evaluation, Friday's audit, the week's meetings, what changed in `OPEN_POINTS.md` and `RECOMMENDATIONS.md`, the money movements per legal entity, the client `STATUS.md` "Now" blocks, and every correction the owner made to the brain's output.
- [ ] **Write `00_Brain/SYSTEM/DREAMS/<yyyy>-W<ww>.md`** with at most three entries in each of five buckets, every entry with its evidence (paths) and the exact change it proposes:
  1. **Notice** — a pattern across days that no single run reported (a client going quiet, a cost creeping, the same question asked twice, a promise slipping).
  2. **Knowledge** — a fact worth a topic note, or a note that the week's evidence made wrong.
  3. **Rules** — a rule two runs applied differently, a rule the owner overrode, a missing rule.
  4. **Routines** — a checklist item to add, merge or drop; a source to reconnect; a new routine as a file in `00_Brain/SCHEDULES/proposed/`.
  5. **For the owner** — an opportunity or a risk with a recommended next step (never a tax or legal conclusion: a question for the adviser instead).
- [ ] Mark the three strongest for Monday's page.

**Sunday — Improve.**
- [ ] Turn Tuesday's three worst findings, Friday's audit findings and Saturday's Rules and Routines entries into **at most five** proposals in `00_Brain/SYSTEM/IMPROVEMENTS.md`: the evidence, the exact change (the file and the new wording), what it costs, how next Tuesday's evaluation will show whether it worked. Typical sources: a source "not read" on three or more days (what to reconnect or replace); a checklist item that was "nothing" for four weeks; something the owner had to ask for by hand that an item should have caught; a rule that two runs applied differently.
- [ ] Check last week's applied changes against this week's evaluation: did the number move? Write one line per change under "Applied": worked, no effect, or made it worse (then propose the way back).
- [ ] Put the three strongest dream entries and the proposals on Monday's `TODO.md` under "The brain suggests", each answerable with `yes`, `no` or a correction.

## Step 4 — the other brains' daily routines

Each linked brain under `Repos/` may keep its own `schedules/daily.md`. This run is their scheduler: for each one that exists, read that file, run it inside that repository, append to that repository's routine log, and put a five-line result into the daily log. Commit and push nothing. A missing routine file is reported as "no routine file" (not an error).

## Step 5 — routine log and final message

Append one entry to `00_Brain/SCHEDULES/ROUTINE_LOG.md`, including the line `block: <name> — done / partly / not run`.

Final message, short: the answer sheet · the three facts that matter most · what needs the owner tomorrow (at most seven lines) · money in and out per legal entity · sources not read and what to do about each · counts · anything skipped and why.

## Rules that decide doubtful cases

- Unknown stays `unknown`, with what would confirm it. No invented date, amount, meeting or document.
- Legal entities never share a line, a sum or a currency column.
- No personal identifiers, access codes or login links in any file or message.
- Never delete; never move an original out of its source; copy.
- No sending, replying, labelling, paying, filing or ticket creation. Drafts only.
- The how of each step is in `.claude/skills/`. Open a skill only when the step you are on needs it; where a skill and this file differ, this file wins.
