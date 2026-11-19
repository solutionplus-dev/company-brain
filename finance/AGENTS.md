# finance — rules for agents working with money

Read the root `AGENTS.md` first; nothing here weakens it.

## What this module is

The finance front door: recurring obligations, the journals per legal entity, and the reports. Originals (invoices, receipts, bank files, tax letters) live in each entity's own folder, `Entity_<CODE>/`.

## Layout

```
finance/
├── SUMMARY.md            the front door: where each entity stands, with certainty labels
├── OBLIGATIONS.md        what comes back every month, quarter, year; one section per entity
├── SEPARATION.md         everything that touches more than one entity, and how it is kept apart
├── ledger/<CODE>/journal_<yyyy>.csv     one folder per entity; a file never holds two
└── reports/<yyyy>/<yyyy-mm>/            weekly and monthly reports, one per entity
```

## Rules here

1. **One entity per file, one currency per column.** Never convert, never sum across entities. A report that shows two entities shows two tables.
2. **Every journal line has a source document** (the `source` column) and a certainty: `statement / proof / calculated / booked / unverified / unknown`.
3. **The entity is the name printed on the document**, never the card or account that paid. A cost one entity paid for another is recorded in `SEPARATION.md` as owed between them.
4. **A payment that matches nothing is `unknown`** and goes to the owner. Never guess a counterparty.
5. **Agents prepare; people file and pay.** A tax return is prepared for the person who files it. No tax or legal conclusion is written as fact: it is a question for the adviser.
6. **Never back-date, never fabricate a document, never "tidy" a journal** by removing a line. A wrong line is corrected by a new line that names it.

## Journal format

`jnl,date,account,account_name,description,debit,credit,currency,counterparty,source,certainty`: one line per side. `python3 tools/index/importers/run_all.py --db .index/vault_index.db --check` reports lines without an amount, a currency or a source, and entries that do not balance.

## Routines that touch it

Daily items 1, 7 to 11; weekly Part A items 2 and 3, Part B.
