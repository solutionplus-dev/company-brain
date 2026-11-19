# 01_Clients — rules for agents working with clients

Read the root `AGENTS.md` first; nothing here weakens it.

## What this module is

One folder per client, named by its slug. `CLIENTS.json` is the register; `WATCHLIST.md` tells the daily run whose mail to look for and what was promised.

## Layout

```
01_Clients/
├── CLIENTS.json          slug, name, kind, billing_entity, stage, updated
├── WATCHLIST.md          senders to watch and promises, per client
├── _TEMPLATE/            copy this for a new client
└── <slug>/
    ├── CLIENT.md         who, billing entity, what we build, contract, risks (changes rarely)
    ├── STATUS.md         "Now" block on top; older blocks in STATUS_HISTORY.md
    ├── Documents/        originals, each with a .digest.md beside it
    ├── Meetings/         index of this client's meetings (the folders live in 02_Meetings/)
    └── Invoices/         copies; the originals are in the billing entity's folder
```

## Rules here

1. **The billing entity is the owner's decision** (`CLIENTS.json`, `DECISIONS.md`). An agent never changes it. `undecided` is a valid value.
2. **A client folder holds only that client.** Nothing about one client is written into another's files.
3. **Confidential and special-category clients.** If a client is under a confidentiality agreement or sends health or similar data: add its folder to `.brainignore` and to the never list in `tools/index/supabase/scopes.json` before filing anything, and do not open, digest or index the data itself.
4. **A promise needs a source.** A date agreed by phone is `NEEDS VERIFICATION` until it is written somewhere.
5. **Clients are named in public only with written consent on file.**
6. **A client project with its own repository** gets its own brain there (scope, plan, deliverables, decisions, risks); this folder keeps billing, contract, invoices and status. One home per fact.

## Routines that touch it

Daily items 4 and 16; weekly Part A item 4, Part C item 12.
