# 02_Meetings — rules for agents filing meetings

Read the root `AGENTS.md` first; nothing here weakens it.

## Layout

```
02_Meetings/
├── registry.json                       one row per meeting
├── <yyyy>/<yyyy-mm-dd>_<slug>/         notes.md · transcript.md (verbatim, if there is one) · attachments
└── MONTH_<yyyy-mm>.md                  rollup of a closed month
```

## Rules here

1. **A meeting folder is a record: its path never changes.**
2. **`notes.md` has five parts:** summary, decisions, actions (with owner), money signals, open questions. A decision also gets a row in `00_Brain/DECISIONS.md`; an action also gets a line in `00_Brain/OPEN_LOOPS.md`.
3. **The transcript is verbatim.** Never correct, shorten or translate it in place. Speakers the source does not name stay unnamed; a guess is marked as a guess.
4. **Not company business, not filed.** A private call, or one that is not this company's business, gets no title, no row and no quote.
5. **A registry row never holds participant names or addresses.** Roles are in `00_Brain/PEOPLE.md`.
6. **Nothing is invented.** A meeting with no recording and no notes is listed in `00_Brain/CALENDAR.md` as a gap, not reconstructed.

## Registry row

`id`, `title`, `date`, `time_local`, `duration_min`, `client` (slug or null), `type` (client | prospect | internal | vendor | excluded), `platform`, `path`, `has_transcript`, `has_notes`, `decisions`.
