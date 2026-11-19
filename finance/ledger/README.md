# Ledger

One folder per legal entity, named by its code from `brain.config.json`. One CSV per year:

```
jnl,date,account,account_name,description,debit,credit,currency,counterparty,source,certainty
```

- One line per side; an entry balances per currency.
- `source` is the path of the document that proves the line.
- `certainty` is one of `statement / proof / calculated / booked / unverified / unknown`.
- A wrong line is corrected by a new entry that names it. Lines are never removed.

If your bookkeeping lives in a tool, export its journal here on the weekly run; the tool stays the system of record and this copy makes the money searchable.
