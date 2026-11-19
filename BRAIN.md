# The map

Read `AGENTS.md` first. This page says where to go for what.

| I want to… | Go to |
|---|---|
| know what the owner must do today | `TODO.md` |
| know what is due | `00_Brain/DEADLINES.md`, `finance/OBLIGATIONS.md` |
| know what is open | `00_Brain/OPEN_LOOPS.md`, `00_Brain/OPEN_POINTS.md` |
| see what happened on a day | `00_Brain/DAILY/<yyyy>/<yyyy-mm>/<date>.md` (the answer sheet is at the top) |
| see what a run read and did not read | `00_Brain/SCHEDULES/ROUTINE_LOG.md` |
| find a client's state | `01_Clients/<slug>/STATUS.md`, then `CLIENT.md` |
| find what was decided | `00_Brain/DECISIONS.md` |
| find a meeting | `02_Meetings/registry.json`, then the meeting's folder |
| see the money of one legal entity | `finance/SUMMARY.md`, `finance/ledger/<CODE>/` |
| know which file owns a fact | `00_Brain/SYSTEM/SYSTEM_OF_RECORDS.md` |
| change what a routine does | edit `00_Brain/SCHEDULES/daily.md` or `weekly.md` |
| propose a rule change | `00_Brain/SYSTEM/IMPROVEMENTS.md` |
| read what the brain thought about last week | `00_Brain/SYSTEM/DREAMS/` |
| search | `scripts/brain ask "<question>"` |

## The five ideas

1. **Files are the memory.** Nothing important lives only in a chat or a tool.
2. **One home per fact.** Every kind of fact has one owning file; everything else points to it.
3. **Two routines, as files.** A daily checklist and a weekly review. A person can read exactly what the agent will do.
4. **Honest gaps.** "Not read" and "unknown" are answers. A guess is not.
5. **It maintains and improves itself, on approval.** It compacts old material, never deletes, and proposes changes to its own rules that only a yes applies.
