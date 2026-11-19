# 00_Brain — rules for agents working in the core

Read the root `AGENTS.md` first; nothing here weakens it.

## What this module is

The operating memory: the registers every run reads and writes, the two schedules, the logs of what ran, distilled knowledge, the archive of rolled-over registers, and `SYSTEM/` (how the brain itself works). It holds no legal or finance originals.

## What it owns

Dated deadlines (`DEADLINES.md`), open actions (`OPEN_LOOPS.md`), decisions (`DECISIONS.md`), recommendations (`RECOMMENDATIONS.md`), people and roles (`PEOPLE.md`), what runs when (`SCHEDULES/*.md`), what each run did (`SCHEDULES/ROUTINE_LOG.md`), contradictions nobody may settle alone (`OPEN_POINTS.md`), mail owed (`EMAIL_BACKLOG.md`), calendar gaps (`CALENDAR.md`), where each source is read (`SOURCES.md`), topic knowledge (`KNOWLEDGE/`).

## Rules here

1. **Open loops.** Any run adds `- [ ] date · owner · action · due · source`. A line is ticked only with a date and evidence, never deleted.
2. **The routine log is append only.** One entry per run with the preflight result and each item's state.
3. **Open points.** A contradiction you cannot settle from evidence becomes a new numbered `OP-nnn` row with both sources. Never pick a side. Only the weekly run closes a point, and only on a document, a ledger entry or the owner's written answer.
4. **Decisions.** A `DEC-` number is never reused and a row is never edited.
5. **Recommendations.** Only the daily and weekly runs give out `REC-` numbers; every recommendation carries its evidence.
6. **Improvements only on the owner's yes** (`SYSTEM/IMPROVEMENTS.md`). A new routine is a file in `SCHEDULES/proposed/`; a switched-off one moves to `SCHEDULES/retired/` with the reason.
7. **Logs go straight into their month folder** (`<yyyy>/<yyyy-mm>/`).
8. **Registers roll over by proposal** (`tools/vault_health/rollover.py stage`); switching a live register needs the owner's approval.
9. **Knowledge.** A fact with an owning file goes there, not into `KNOWLEDGE/`.
10. **INBOX.** File what arrives by copying it to its home and appending to `INBOX/FILED.md`; never delete the drop.

## Never

- Never edit or reorder a past routine-log entry, a closed `OP-` row or a `DEC-` number.
- Never apply an improvement, a new schedule or a register rollover without the owner's yes.
- Never write "nothing new" for a source that was not read.
