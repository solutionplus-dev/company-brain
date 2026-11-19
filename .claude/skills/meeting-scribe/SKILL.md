---
name: meeting-scribe
description: File a meeting into 02_Meetings — verbatim transcript, structured notes, registry row, decisions and actions into their registers. Use for "ingest meeting", "file today's call", a notetaker id, or daily items 12 and 13.
---

# Filing a meeting

1. Is it company business? If not: no folder, no row, no quote.
2. Folder `02_Meetings/<yyyy>/<yyyy-mm-dd>_<slug>/`.
3. `transcript.md`: verbatim, in the order spoken, speakers as the source names them. Unnamed stays unnamed.
4. `notes.md` from `_TEMPLATE/notes.md`: summary, decisions, actions with owners, money signals, open questions. Only what was said.
5. Registry row in `registry.json` (no participant names).
6. Each decision → a new `DEC-` row in `00_Brain/DECISIONS.md`. Each action → a line in `00_Brain/OPEN_LOOPS.md`. A client's request → that client's `STATUS.md`.
7. A candidate decision the meeting did not clearly take is listed as a candidate for the owner, not logged as decided.
