# Schedules

Two, and no more without the owner's yes. The scheduler's whole prompt is: *"Read `00_Brain/SCHEDULES/<file>` and execute it."*

| Run | Cadence | File | What it does |
|---|---|---|---|
| Daily | every day, evening (`30 21 * * *`) | `daily.md` | preflight, 19 checks, answer sheet, tomorrow's page, registers, index |
| Weekly | Monday morning (`0 8 * * 1`) | `weekly.md` | week and month ahead, finance week, cleanup and compaction, audit, the dream, improvement proposals |

**The self-improvement loop lives inside the daily run**, one block per weekday, about 15 minutes, each with its own checklist and a file as its result (`daily.md` Step 3b):

| Day | Block | Result |
|---|---|---|
| Monday | Apply what the owner answered | `SYSTEM/IMPROVEMENTS.md` "Applied" |
| Tuesday | Evaluate the week (sources read, answer sheet, owner corrections, `scripts/brain check`) | `SYSTEM/EVALUATIONS/<yyyy>-W<ww>.md` |
| Wednesday | Enrich (digests, one knowledge note, one client file, new obligations) | the files themselves |
| Thursday | Clean up (sizes, rollovers prepared, loose files, rollups) | `ARCHIVE/_proposed/`, lists for the owner |
| Friday | Audit (the brain against itself, one home per fact, linked brains) | `AUDITS/<yyyy>/<yyyy-mm>/` |
| Saturday | Dream (five buckets, propose only) | `SYSTEM/DREAMS/<yyyy>-W<ww>.md` |
| Sunday | Improve (at most five proposals; did last week's change work?) | `SYSTEM/IMPROVEMENTS.md` "Proposed" |

Monday's weekly run reads the six results into the week ahead and catches up any block that did not end `done`; the dream is never skipped.

- `ROUTINE_LOG.md` — one appended entry per run. Never edited.
- `proposed/` — a routine the brain suggests, as a file. It runs only after the owner writes `active` into it.
- `retired/` — a routine that was switched off, with the reason and the date.

Both runs, the weekday loop and the life of a proposal are drawn in `docs/DIAGRAMS.md` (diagrams 2, 3, 9, 10 and 11).

Why files: a person can read exactly what the agent will do, change it with a text editor, and see in version history when it changed.
