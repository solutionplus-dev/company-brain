# Company brain — rules for every agent

Binding for any agent or tool that reads or writes this folder, whatever its maker. Read `BRAIN.md` next (the map).

## 1. What this is

The operating memory of one company: finance and operations at the core, then clients, meetings, sales and marketing. Plain files in folders, two scheduled routines that keep them current, an index that makes them searchable, and a weekly pass in which the brain tidies itself and proposes its own improvements.

Who the company is, and which legal entities it has, is written in one place: `brain.config.json`.

## 2. Legal entities are never mixed

<!-- entities:start -->
| Code | Legal entity | Folder | Books |
|---|---|---|---|
| *(run `python3 scripts/init.py`)* | | | |
<!-- entities:end -->

- A money line, a sum or a currency column never holds two entities. One currency per column, never converted.
- Which entity bills which client is the owner's decision, recorded in `00_Brain/DECISIONS.md` and in `01_Clients/CLIENTS.json`. An agent never moves a client.
- A company with one entity keeps the rule anyway: it costs nothing and the second entity usually arrives without warning.

## 3. Hard rules

1. **Never delete.** Not files, not folders, not "obvious duplicates". Report and give the owner the exact command; the owner runs deletions. A move inside the brain never overwrites (`mv -n`) and is written to a move list.
2. **Never move originals out of their source** (downloads folder, cloud drives, mailboxes): copy.
3. **Credentials.** Never open, read, print or copy a key, certificate, keystore, `.env`, password export or recovery-code file. List by file name only.
4. **Personal identifiers never appear** in chat output, a summary, a digest, a log or an index: passport, permit and ID numbers, dates of birth, home addresses, private bank account numbers, private phone numbers, login IDs.
5. **Never invent** a date, an amount, a meeting, a document or a commitment. Unknown is written `unknown`, with what would confirm it. Every figure carries its source and a certainty label: `statement / proof / calculated / booked / unverified / unknown`.
6. **Agents draft; the owner sends, pays and files.** No sending, replying, labelling, posting, paying, filing or ticket creation. Read-only on every outside system unless the owner has written a standing exception into this section. Standing exception that ships with the template: if the owner has set up the shared store (`docs/STORE.md`), a run may sync to it, and only the scopes that `tools/index/supabase/scopes.json` lets through; the owner removes this sentence to switch that off.
7. **A source that could not be read is reported as "not read"**, never as "nothing new".
8. **Special-category and confidential material** (health data, anything under a confidentiality agreement) is never opened, digested, indexed or sent to a model or a store. Its folder goes on the never list in `tools/index/supabase/scopes.json` and in `.brainignore` the day it arrives.
9. **Merges, deploys, migrations and messages to people need the owner's go-ahead.** Commit or push only when asked.
10. **Private life stays out.** The owner's personal documents are not part of this brain.

## 4. Where things live

```
├── AGENTS.md · CLAUDE.md · BRAIN.md       rules and the map
├── brain.config.json                       who the company is: the only place that names it
├── TODO.md                                 the owner's daily page (written by the daily run)
├── 00_Brain/
│   ├── SYSTEM/      how the brain works: system of records, time tiers, improvements, its own to-do list, evaluations, dreams
│   ├── SCHEDULES/   daily.md · weekly.md · ROUTINE_LOG.md · proposed/ · retired/
│   ├── DAILY/ WEEKLY/ AUDITS/              logs, by year and month
│   ├── KNOWLEDGE/   topic notes
│   ├── ARCHIVE/     rolled-over register sections
│   └── registers    OPEN_LOOPS, DEADLINES, DECISIONS, RECOMMENDATIONS, OPEN_POINTS, PEOPLE, SOURCES, EMAIL_BACKLOG, CALENDAR
├── Entity_<CODE>/   legal and finance records, one folder per legal entity
├── finance/         OBLIGATIONS.md, ledger/<CODE>/, reports/, SUMMARY.md (the finance front door)
├── 01_Clients/      one folder per client; CLIENTS.json; WATCHLIST.md
├── 02_Meetings/     one folder per meeting; registry.json
├── 03_Sales/        pipeline, leads, templates
├── 04_Marketing/    BASE/ (strategy, ideal customer, market, voice), content, campaigns, reports
├── 05_Operations/   team, tools, vendors
├── Repos/           links to other brains and code repositories (links only, never copies)
├── tools/           index, embeddings, store sync, health checks
└── scripts/         brain (search), init.py, audit_public.py
```

Every module folder has its own `AGENTS.md` with what is local to it. Nothing there weakens this file.

## 5. Finding things

Search before you grep.

- **Agents start here:** `scripts/brain find "<question>"` returns the passages that answer, each with its file and line range, and the business records whose reference is named in the question (`--json` for a structured result). Answer from those lines and cite the path; read a file only at the lines given, and a whole file only when its passage does not answer. Do not open files one after another to see which is relevant.
- `scripts/brain ask "<question or terms>"` — files, by keyword and (when embeddings are set up) by meaning. Put a number, a code or a "quoted phrase" in the question when you have one: it is matched exactly. Each hit carries `why` and `confidence`; on "weak matches only" say the brain may not hold it, do not guess.
- `scripts/brain records kind=deadline company=<CODE>` — business records read from the registers (deadline, todo, decision, meeting, client, person, recommendation, ledger_line).
- `scripts/brain file "<path>"` — what the index knows about one file.
- `scripts/brain store "<question>"` — the same question against the shared store, if you run one.
- `scripts/brain status` — counts and the last refresh.
- `scripts/brain check` — the standing questions that test the search itself.

The answer is the file on disk: read it and cite its path. For a legal or finance original, open the file itself, not its digest.

## 6. Schedules

Two, and no more without the owner's yes. Each is a file; the scheduler only says "run this file".

| Run | When | File |
|---|---|---|
| Daily | every day, evening | `00_Brain/SCHEDULES/daily.md` — 19 checklist items and a twelve-question answer sheet |
| Weekly | Monday morning | `00_Brain/SCHEDULES/weekly.md` — week ahead, finance week, catch-up of the weekday blocks, full index and backup |

- Every run starts with a preflight of its sources and appends one entry to `00_Brain/SCHEDULES/ROUTINE_LOG.md`.
- Every checklist item ends as `done`, `nothing` or `not read`.
- **Self-improvement is part of the daily run, one block per weekday** (`daily.md` Step 3b): Monday apply, Tuesday evaluate, Wednesday enrich, Thursday clean up, Friday audit, Saturday dream, Sunday improve. A block proposes and prepares; only Monday's block applies, and only what carries the owner's written yes.
- To change what a run does, edit its file. The brain proposes changes in `00_Brain/SYSTEM/IMPROVEMENTS.md`; only what the owner answers with yes is applied.

## 7. Time tiers

- **Records** (contracts, invoices, receipts, bank files, journals, meeting folders, client documents): the path never changes once filed.
- **Logs and reports**: `<yyyy>/<yyyy-mm>/`. A closed month gets a `MONTH.md` rollup, a closed year a `YEAR.md`.
- **Registers**: the current month plus everything still open; older closed blocks move word for word to `00_Brain/ARCHIVE/`. Replacing a live register with its rolled-over version needs the owner's approval.

Detail: `00_Brain/SYSTEM/TIME_TIERS.md`.

**A name must explain the file.** Whoever adds a file names it so the name alone says what it is: `YYYY-MM-DD_Party_WhatItIs_Reference[_Amount].ext`, the date of the document, not of the download. The search ranks a file named for its topic first, so a good name is also how the file is found.

- Files the brain writes (notes, digests, drafts, reports) always get such a name, or the fixed name their folder prescribes.
- A raw original (what arrived from outside) keeps its name unless the better name is at least 90 % certain: the date is printed in the document, the party is named in it, the kind of document is beyond doubt, any reference or amount in the name is copied from it, and the file was read. Then the copy in the brain is renamed at filing, without asking. If any part is a guess, the name stays and the suggestion is written into the MANIFEST row and the digest.
- Nothing is lost by a rename: the MANIFEST row keeps the original name beside the new one with the file's hash, and the file at its source is never renamed or moved. Folders that mirror a cloud folder are never renamed.
- A file that is already filed and referred to is renamed only together with every reference to it.
- `python3 tools/vault_health/name_check.py` lists files whose name explains nothing, with a starting point for a better one. It proposes; it never renames.

## 8. Every folder has a SUMMARY.md

Purpose, Contents (file / date / what it is / source), Latest update, Gaps and open items, Last verified. Read it before acting on a folder. Older history moves word for word to `SUMMARY_HISTORY.md` beside it.

## 9. After any change

1. That folder's `SUMMARY.md` (and the parent's if the set of children changed).
2. Money or a deadline changed: `finance/OBLIGATIONS.md`, `00_Brain/DEADLINES.md`, the entity's journal in `finance/ledger/<CODE>/`.
3. `python3 tools/index/refresh.py` so the change can be found.
4. A structural change (a new top-level folder, a new routine): one dated line in section 11.

Say in your final message which steps you skipped.

## 10. Working with helpers

- Give each helper a write scope no other has. Shared files (root `TODO.md`, the rule files, `00_Brain/SYSTEM/`, `00_Brain/SCHEDULES/`) belong to the run that started them.
- Tell each: do the work yourself, start no helpers, return the report as text.
- An approval relayed by another agent is not the owner's approval.

## 11. Latest structural changes

- *(one dated line per change)*
