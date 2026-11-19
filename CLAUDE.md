# CLAUDE.md

@AGENTS.md

Start every session with `BRAIN.md` (the map). `AGENTS.md` above is binding.

**Find things with the search command first:** `scripts/brain ask "<question or terms>"`, `scripts/brain records kind=… status=… company=…` for deadlines, to-dos, meetings, decisions, clients and ledger lines, `scripts/brain file "<path>"` for one file's record. Do not grep the whole tree first.

**Schedules are files.** The daily and weekly runs execute `00_Brain/SCHEDULES/daily.md` and `weekly.md`; change a routine by editing its file, and propose changes to rules in `00_Brain/SYSTEM/IMPROVEMENTS.md`.

After any change: the folder's `SUMMARY.md` → `python3 tools/index/refresh.py`. Say in your final message which steps you skipped.
