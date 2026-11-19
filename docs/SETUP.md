# Setup

The whole path as one picture: `docs/DIAGRAMS.md`, diagram 21.

## 1. Initialise

```bash
python3 scripts/init.py
```

It asks for the company name, the time zone, and each legal entity (name, a short code such as `DE`, its main currency). It writes `brain.config.json`, creates `Entity_<CODE>/` and `finance/ledger/<CODE>/`, and fills the entity table in `AGENTS.md`. Run it again any time to add an entity; it never overwrites a file that exists.

## 2. Tell it where to read

Fill in `00_Brain/SOURCES.md`: for each source, which connector, command or folder your agent uses, and a cheap test. No passwords or keys go into that file. List what must never be read (private mailboxes, anything that is not the company's).

Anything you do not connect is reported as "not read" every day. That is by design: you see the gap until you close it.

## 3. Enter what you already know

- `finance/OBLIGATIONS.md`: every recurring duty you can think of, with the reminder mail that announces it.
- `01_Clients/CLIENTS.json` and one folder per client from `01_Clients/_TEMPLATE/`.
- `00_Brain/PEOPLE.md`: roles only.
- `04_Marketing/BASE/`: even three sentences each.

## 4. Build the index

```bash
python3 tools/index/refresh.py --full
scripts/brain status
python3 tests/test_smoke.py
```

## 5. Schedule the two routines

In your agent tool's scheduler, create two tasks whose whole prompt is:

- Daily, every evening: *Read `00_Brain/SCHEDULES/daily.md` and execute it.*
- Weekly, Monday morning: *Read `00_Brain/SCHEDULES/weekly.md` and execute it.*

Run the daily one by hand first and read the result with the routine file beside it.

## 6. The first week

Expect many "not read" and `unknown` answers. Each is a to-do for you (connect a source, find a document), and the weekly run will list them as improvement proposals. By the second Monday the answer sheet should be mostly Yes and No.

## 7. Optional

- Search by meaning: `docs/SEARCH_AND_EMBEDDINGS.md`.
- A shared store for a team: `docs/STORE.md`.
- Back the folder up. The brain reports the age of the last backup every Monday; making one is yours.
