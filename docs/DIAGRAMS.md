# Diagrams

Every moving part of the brain as a picture. The routine files and the code stay the truth: when a diagram and `00_Brain/SCHEDULES/daily.md` disagree, the file is right and the diagram is fixed.

All diagrams are Mermaid, so they render on GitHub and in most editors, and you can change them in a text editor.

| # | Diagram | Kind | Answers |
|---|---|---|---|
| 1 | [The whole system](#1-the-whole-system) | flow chart | What reads what, and where does it end up? |
| 2 | [A day](#2-a-day) | sequence | Who does what between the evening run and the next morning? |
| 3 | [The daily run, step by step](#3-the-daily-run-step-by-step) | flow chart | In which order does the run work, and what is cut first? |
| 4 | [One checklist item](#4-one-checklist-item-done-nothing-or-not-read) | flow chart | When is the answer "nothing" and when "not read"? |
| 5 | [An invoice arrives](#5-an-invoice-arrives) | flow chart | Which legal entity gets it, and where is it filed? |
| 6 | [A payment is matched](#6-a-payment-is-matched) | sequence | When does a journal line get the label `proof`? |
| 7 | [A client asks for something](#7-a-client-asks-for-something) | sequence | Who drafts, who sends, and when is the row ticked? |
| 8 | [A meeting is filed](#8-a-meeting-is-filed) | sequence | What is written after a call, and where? |
| 9 | [The week the brain spends on itself](#9-the-week-the-brain-spends-on-itself) | flow chart | How does it improve without changing its own rules? |
| 10 | [The life of a proposal](#10-the-life-of-a-proposal) | state | What happens after a yes, a no, or silence? |
| 11 | [Monday: the weekly run and its catch-up](#11-monday-the-weekly-run-and-its-catch-up) | flow chart | What does Monday repeat, and what does it only read? |
| 12 | [The dream](#12-the-dream) | flow chart | What does it read, and what may it change? |
| 13 | [Two files disagree](#13-two-files-disagree) | flow chart | Which file wins? |
| 14 | [How old material is folded](#14-how-old-material-is-folded) | flow chart and state | How does the brain stay small without deleting? |
| 15 | [Building the index](#15-building-the-index) | flow chart | What happens on `refresh.py`? |
| 16 | [A search](#16-a-search) | sequence | How do keywords and meaning come together? |
| 17 | [What may leave the computer](#17-what-may-leave-the-computer) | flow chart | Which gates does a file pass before the shared store? |
| 18 | [Reading the shared store](#18-reading-the-shared-store) | sequence | What does a team member see, and what does a stranger get? |
| 19 | [The data model](#19-the-data-model) | entity relationship | Which tables exist, locally and in the store? |
| 20 | [Several brains, one scheduler](#20-several-brains-one-scheduler) | flow chart | How do linked brains hang together? |
| 21 | [Setup and the first two weeks](#21-setup-and-the-first-two-weeks) | flow chart | What do I do first? |

At the end: [how to draw your own](#drawing-your-own).

---

## 1. The whole system

Sources are read by two routines. The routines write plain files. The index is built from the files, never the other way round.

```mermaid
flowchart LR
  subgraph S["Sources (read only)"]
    S1["Mailboxes"]
    S2["Bank messages"]
    S3["Invoicing and bookkeeping tools"]
    S4["Notetaker and recordings"]
    S5["Calendar"]
    S6["Downloads and INBOX"]
  end

  subgraph R["Two routines, each a file"]
    R1["daily.md<br/>every evening"]
    R2["weekly.md<br/>Monday morning"]
  end

  subgraph F["Plain files (the truth)"]
    F1["Registers<br/>deadlines, open loops, obligations"]
    F2["Logs<br/>daily, weekly, routine log"]
    F3["Client files"]
    F4["Journals per legal entity"]
    F5["Originals with a digest beside them"]
  end

  subgraph I["Index (rebuilt from the files)"]
    I1["Catalogue and full-text search"]
    I2["Business records"]
    I3["Embeddings, optional"]
  end

  S --> R1
  S --> R2
  R1 --> F
  R2 --> F
  F --> I
  I --> Q["scripts/brain<br/>ask, records, file, check"]
  I -. "optional, by scope" .-> ST["Shared store"]
  F --> T["TODO.md<br/>the owner's page"]
  T --> O(["Owner<br/>sends, pays, signs, files"])
  O -. "yes, no or a correction" .-> F
```

## 2. A day

The agent reads and files in the evening. The owner acts in the morning. Nothing is sent by the agent.

```mermaid
sequenceDiagram
  autonumber
  participant SCH as Scheduler
  participant AG as Agent
  participant SRC as Sources
  participant FS as Files
  participant IDX as Index
  actor OWN as Owner

  SCH->>AG: Read daily.md and execute it
  AG->>FS: Read the last routine-log entry (start of the window)
  AG->>FS: Write the skeleton of today's daily log
  AG->>SRC: Preflight, one cheap call per source
  SRC-->>AG: read, or not read with the error
  AG->>SRC: Gather mail, bank messages, meetings, calendar, new files
  SRC-->>AG: Findings with message id, date and amount as written
  AG->>FS: File invoices, post and meetings, each with a digest
  AG->>FS: Write the answer sheet, the daily log and TODO.md
  AG->>FS: Update the registers and the client files
  AG->>IDX: refresh.py
  IDX-->>AG: Counts
  AG->>FS: Today's self-improvement block and its result file
  AG->>FS: Append one entry to the routine log
  AG-->>OWN: Final message, the answer sheet first
  Note over OWN: Next morning
  OWN->>FS: Open TODO.md, at most seven actions
  OWN->>SRC: Send, pay, sign and file
  OWN->>FS: Answer proposals with yes, no or a correction
```

## 3. The daily run, step by step

The dotted line is the order of sacrifice when time or tools run short. The answer sheet, the daily log, `TODO.md` and the routine-log entry are never cut.

```mermaid
flowchart TD
  A["Step 0<br/>window, skeleton, preflight"] --> B{"Did every source answer?"}
  B -- "yes" --> C["Step 1<br/>gather"]
  B -- "no" --> B1["Mark the source not read,<br/>with the error and what the owner must do"]
  B1 --> C
  C --> D["Step 2, items 1 to 6<br/>mail"]
  D --> E["Items 7 to 11<br/>money, one legal entity at a time"]
  E --> G["Items 12 to 14<br/>meetings and calendar"]
  G --> H["Items 15 and 16<br/>deadlines and promises"]
  H --> J["Item 17<br/>new files"]
  J --> K["Step 3<br/>answer sheet, daily log, TODO.md, registers"]
  K --> L["Items 18 and 19<br/>syncs and summaries"]
  L --> M["Step 3b<br/>today's self-improvement block"]
  M --> N["Step 4<br/>the linked brains' daily routines"]
  N --> P["Step 5<br/>routine log and final message"]

  X["Short of time?"] -. "cut first" .-> N
  X -. "cut second" .-> M
  X -. "cut third: item 16" .-> H
  X -. "and item 17" .-> J
```

## 4. One checklist item: done, nothing or not read

The rule behind the answer sheet. A source that failed is never reported as "nothing new".

```mermaid
flowchart TD
  A["A checklist item"] --> B{"Was its source read?"}
  B -- "no" --> NR["not read<br/>with the exact error"]
  B -- "yes" --> C{"Was something found?"}
  C -- "no" --> NO["nothing"]
  C -- "yes" --> D{"Is the fact on a document?"}
  D -- "yes" --> DN["done<br/>the figure with its source and a certainty label"]
  D -- "no" --> UK["done<br/>the figure stays unknown, with what would confirm it"]
  NR --> S["Answer sheet: Not read"]
  NO --> S2["Answer sheet: No"]
  DN --> S3["Answer sheet: Yes"]
  UK --> S3
```

## 5. An invoice arrives

The legal entity comes from the name printed on the invoice, never from the card that paid. Each entity has its own folders, its own journal and its own section in the daily log.

```mermaid
flowchart TD
  A["An invoice or receipt in the mail<br/>or in the downloads folder"] --> B{"Which name is printed on it?"}
  B -- "entity A" --> C1["Copy to Entity_A/Expenses/yyyy/yyyy-mm/"]
  B -- "entity B" --> C2["Copy to Entity_B/Expenses/yyyy/yyyy-mm/"]
  B -- "not clear" --> C3["Leave it where it is,<br/>one row in OPEN_POINTS.md"]
  C1 --> D1["MANIFEST row and a digest beside the PDF"]
  C2 --> D2["MANIFEST row and a digest beside the PDF"]
  D1 --> E1["Daily log: Money, entity A<br/>to pay, with its due date"]
  D2 --> E2["Daily log: Money, entity B<br/>to pay, with its due date"]
  E1 -. "only when the bank proves the payment" .-> F1["finance/ledger/A/journal"]
  E2 -. "only when the bank proves the payment" .-> F2["finance/ledger/B/journal"]
  C3 --> G["TODO.md: a question for the owner"]
```

The two columns never meet: no line, no sum and no currency column holds both entities. An invoice that arrived is filed and listed as to pay; it becomes a journal line only with the bank's proof (next diagram).

## 6. A payment is matched

```mermaid
sequenceDiagram
  autonumber
  participant BANK as Bank message
  participant AG as Agent
  participant INV as Open invoices
  participant JR as Journal of that entity
  participant TD as TODO.md
  actor OWN as Owner

  AG->>BANK: Search by sender, every run
  BANK-->>AG: Date, amount, currency, counterparty, reference
  AG->>INV: Look for an open invoice with this amount and reference
  alt The bank message proves the payment
    INV-->>AG: One invoice matches
    AG->>JR: Add the line with certainty proof and the message as source
  else An invoice fits but the message does not prove it
    INV-->>AG: A likely match
    AG->>TD: Say what is missing, leave the journal alone
  else Nothing matches
    INV-->>AG: No invoice
    AG->>TD: Payment is unknown, goes to the owner
    Note over AG,OWN: No journal line is guessed. It waits for the owner's answer.
  end
```

## 7. A client asks for something

The agent writes the request down and drafts. The owner sends. The row is ticked only when the reply is visible in sent mail.

```mermaid
sequenceDiagram
  autonumber
  actor CL as Client
  participant MB as Mailbox
  participant AG as Agent
  participant ST as Client STATUS.md
  participant BL as EMAIL_BACKLOG.md
  participant TD as TODO.md
  actor OWN as Owner

  CL->>MB: A message that asks for something
  AG->>MB: Read every folder, drafts and junk included
  AG->>AG: Is the sender on the watchlist?
  AG->>ST: Write what, by when, into the Now block
  AG->>BL: Add a row, reply owed
  AG->>TD: Put it on tomorrow's page with the reason and the file
  OWN->>MB: Write and send the reply
  Note over AG: Next evening
  AG->>MB: Look in sent mail
  alt The reply is there
    AG->>BL: Tick the row
  else Older than 24 hours and no reply
    AG->>TD: Keep it on the page, one day older
  end
```

## 8. A meeting is filed

```mermaid
sequenceDiagram
  autonumber
  participant NT as Notetaker or recording
  participant AG as Agent
  participant MF as Meeting folder
  participant RG as registry.json
  participant CS as Client STATUS.md
  participant DC as DECISIONS.md
  participant OL as OPEN_LOOPS.md

  AG->>NT: Meetings inside the window
  NT-->>AG: Title, time, participants, transcript
  alt Company business
    AG->>MF: notes.md with summary, decisions, actions, money signals, open questions
    AG->>RG: One row, so the meeting exists once
    AG->>CS: What changed for that client
    AG->>DC: Each decision, with the meeting as its source
    AG->>OL: Each action with an owner and a date
  else Not company business
    AG->>AG: No content is kept
  end
  Note over AG,NT: If the notetaker and a local recording both have the call, the notetaker wins
```

## 9. The week the brain spends on itself

One block a day inside the daily run, about fifteen minutes each. A block proposes and prepares. Only Monday applies, and only what carries a written yes.

```mermaid
flowchart LR
  TUE["Tuesday<br/>Evaluate<br/>score the week and the search"] --> WED["Wednesday<br/>Enrich<br/>digests, one note, one client file"]
  WED --> THU["Thursday<br/>Clean up<br/>sizes, rollovers prepared, loose files"]
  THU --> FRI["Friday<br/>Audit<br/>the brain against itself"]
  FRI --> SAT["Saturday<br/>Dream<br/>five buckets, propose only"]
  SAT --> SUN["Sunday<br/>Improve<br/>at most five proposals"]
  SUN --> OWN{{"Owner answers<br/>yes, no or a correction"}}
  OWN --> MON["Monday<br/>Apply<br/>only what carries a yes"]
  MON --> TUE

  TUE -. "writes" .-> E[("EVALUATIONS/yyyy-Www.md")]
  FRI -. "writes" .-> A[("AUDITS/yyyy/yyyy-mm/")]
  SAT -. "writes" .-> D[("DREAMS/yyyy-Www.md")]
  SUN -. "writes" .-> P[("IMPROVEMENTS.md")]
  E -. "three worst findings" .-> SUN
  A -. "findings" .-> SUN
  D -. "rules and routines" .-> SUN
  E -. "did last week's change move the number?" .-> SUN
```

## 10. The life of a proposal

```mermaid
stateDiagram-v2
  [*] --> Proposed: Sunday writes it with evidence and the exact change
  Proposed --> Applied: the owner writes yes, Monday applies it
  Proposed --> Declined: the owner writes no, with the reason
  Proposed --> Proposed: the owner writes a correction
  Proposed --> AskedAgain: no answer for two weeks, asked once more
  AskedAgain --> Applied: yes
  AskedAgain --> Declined: no
  AskedAgain --> Waiting: still no answer, parked under Waiting
  Applied --> Worked: next Tuesday's number moved
  Applied --> NoEffect: the number did not move
  Applied --> MadeItWorse: the number got worse
  MadeItWorse --> Proposed: the way back is proposed
  Worked --> [*]
  NoEffect --> [*]
  Declined --> [*]
```

## 11. Monday: the weekly run and its catch-up

Part A is written first so that it exists even if a later part fails. A block that already ended `done` during the week is read, not repeated.

```mermaid
flowchart TD
  A["Read the last seven routine-log entries"] --> B["Step 0<br/>skeleton and preflight"]
  B --> PA["Part A<br/>the week and the month ahead, written first"]
  PA --> PB["Part B<br/>finance week, one legal entity at a time"]
  PB --> M{"First Monday of a month?"}
  M -- "yes" --> MC["Month close per entity"]
  M -- "no" --> CU
  MC --> CU{"For each weekday block:<br/>did it end done?"}
  CU -- "done" --> RD["Read its result into Part A"]
  CU -- "partly or not run" --> RUN["Do it now<br/>Part C clean up, Part D audit,<br/>Part G dream, Part H improve,<br/>evaluate and enrich by daily.md Step 3b"]
  RD --> PE
  RUN --> PE["Part E<br/>full index, store sync, backup age"]
  PE --> PF["Part F<br/>the linked brains' weekly routines"]
  PF --> W["Weekly file, Monday's TODO.md,<br/>routine log, final message"]
  W --> EV["Monday evening's daily run<br/>applies what the owner answered"]
```

## 12. The dream

Once a week the brain reads everything and thinks about the company while nobody is asking. It changes nothing.

```mermaid
flowchart LR
  subgraph IN["It reads the whole week"]
    I1["Seven daily logs and answer sheets"]
    I2["Routine log"]
    I3["Meetings"]
    I4["Open points and recommendations"]
    I5["Money per legal entity"]
    I6["Client Now blocks"]
    I7["Every correction the owner made"]
  end

  IN --> DR["DREAMS/yyyy-Www.md<br/>at most three entries per bucket,<br/>each with evidence and the exact change"]

  DR --> B1["Notice<br/>a pattern no single run reported"]
  DR --> B2["Knowledge<br/>a note to write or to correct"]
  DR --> B3["Rules<br/>unclear, overridden or missing"]
  DR --> B4["Routines<br/>an item to add, merge or drop"]
  DR --> B5["For the owner<br/>an opportunity or a risk"]

  DR --> TOP["The three strongest entries,<br/>from any bucket"]
  B3 --> IMP["IMPROVEMENTS.md<br/>as proposals"]
  B4 --> IMP
  TOP --> TD["Monday's TODO.md<br/>The brain suggests"]
  IMP --> TD
```

## 13. Two files disagree

Every kind of fact has one owning file (`00_Brain/SYSTEM/SYSTEM_OF_RECORDS.md`). Everything else links to it.

```mermaid
flowchart TD
  A["The same fact in two files,<br/>with different values"] --> B["Look up the owning file"]
  B --> C{"Is there evidence that settles it?<br/>a document, a ledger entry,<br/>the owner's written answer"}
  C -- "yes, and the owning file is right" --> D["Correct the other file to link, not restate"]
  C -- "yes, and the owning file is wrong" --> E["Correct the owning file, name the evidence"]
  C -- "no" --> F["New row in OPEN_POINTS.md<br/>both paths, both values"]
  F --> G["Weekly run, Part A<br/>decisions waiting for the owner"]
  G --> H{"Settled?"}
  H -- "yes" --> I["Moved word for word to<br/>ARCHIVE/OPEN_POINTS_closed.md"]
  H -- "no" --> G
```

## 14. How old material is folded

Nothing is removed. What is current is found first; what is old is one step further away.

```mermaid
flowchart LR
  D["A day<br/>daily log, report"] --> M["Month closes<br/>MONTH.md rollup"]
  M --> Y["Year closes<br/>YEAR.md rollup"]
  Y --> Z["Older than two years<br/>month folders may be zipped,<br/>after telling the owner"]

  R["Records<br/>contracts, invoices, journals, meetings"] --> R1["The path never changes.<br/>Hidden by indexes and rollups, not by moving."]
  AR["_archive and 00_Brain/ARCHIVE"] --> AR1["Kept and indexed with tier archive.<br/>Left out of default searches."]
```

A register (open loops, deadlines, mail backlog) holds the current month and everything still open. Older closed blocks roll over, by proposal:

```mermaid
stateDiagram-v2
  [*] --> WithinBudget
  WithinBudget --> OverBudget: size_check.py reports it
  OverBudget --> Staged: rollover.py stage writes a proposal to ARCHIVE/_proposed
  Staged --> Staged: the owner has not answered, the live register stays as it is
  Staged --> Switched: the owner writes yes
  Switched --> WithinBudget: closed blocks now live word for word in ARCHIVE
```

## 15. Building the index

`python3 tools/index/refresh.py`. Incremental every day, `--full` on Monday. A failure in the importers or the embedder is recorded and never stops the run.

```mermaid
flowchart TD
  A["Walk the indexed folders"] --> B0{"Matched by .brainignore?"}
  B0 -- "yes" --> X["Not catalogued at all"]
  B0 -- "no" --> C["Hash each file, sha256"]
  C --> D{"Compared with the catalogue"}
  D -- "new" --> E["Add a row"]
  D -- "changed" --> F["Update the row"]
  D -- "same hash at a new path" --> G["A move: the row keeps its identity"]
  D -- "gone" --> H["Remove the row"]
  E --> K["Catalogue and full-text search<br/>path, name, purpose, digest text"]
  F --> K
  G --> K
  H --> K
  K --> L["Importers read the registers<br/>deadlines, to-dos, decisions, meetings,<br/>clients, people, obligations, ledger lines"]
  L --> M["records table<br/>each with its source path and line"]
  M --> N{"Embedding set up?"}
  N -- "no" --> O["A note in the run: search stays keyword-only"]
  N -- "yes" --> P0{"May this file be embedded?<br/>no credentials, no identity documents,<br/>no guarded client folder"}
  P0 -- "no" --> PX["Catalogued by name only, never embedded"]
  P0 -- "yes" --> P["Its text, or the text of its digest"]
  P --> Q["Redact<br/>phones, private addresses, ID and account numbers"]
  Q --> R["Chunks of about 1,200 characters, with overlap"]
  R --> S["Embed on the laptop"]
  S --> T["vectors.db<br/>sign bits, 96 bytes<br/>and the 8-bit vector"]
  O --> U["One row in the runs table"]
  T --> U
  PX --> U
```

## 16. A search

```mermaid
sequenceDiagram
  autonumber
  actor U as Person or agent
  participant B as scripts/brain ask
  participant Q as query.py
  participant FTS as Full-text search
  participant E as Embedder
  participant V as vectors.db

  U->>B: A question in plain words
  B->>Q: The question, with area, tier or entity filters
  Q->>FTS: Keyword query
  FTS-->>Q: Ranked paths
  opt Embeddings are set up
    Q->>E: Embed the question on the laptop
    E->>V: Compare sign bits with every chunk (Hamming distance)
    V-->>E: The best 300
    E->>V: Exact score on those 300 with the 8-bit vectors
    V-->>E: Ranked chunks with their paths
    E-->>Q: Ranked paths
    Q->>Q: Fuse both lists by reciprocal rank (k = 60)
  end
  Q-->>B: Paths, titles, snippets
  B-->>U: The answer is the file: read it and cite its path
```

## 17. What may leave the computer

Only for the optional shared store. One file decides: `tools/index/supabase/scopes.json`. File bytes never go up, only text chunks from text files and digests, their embeddings, and records.

```mermaid
flowchart TD
  A["A file in the index"] --> B{"On the never list?<br/>path, folder name or file name pattern"}
  B -- "yes" --> STAY["Stays local.<br/>No row, no chunk, no record."]
  B -- "no" --> C{"Does a rule give it a scope?"}
  C -- "no rule, or scope null" --> STAY
  C -- "yes" --> D{"Is the scope private?<br/>finance, ops, client"}
  D -- "no: gtm, outreach, templates, design" --> G
  D -- "yes" --> E{"owner_confirmed_private_scopes is true?"}
  E -- "no" --> REF["Refused, whatever the command line says"]
  E -- "yes" --> F{"A client scope?"}
  F -- "no" --> G
  F -- "yes" --> F2{"Is its slug in client_scopes_allowed?"}
  F2 -- "no" --> REF
  F2 -- "yes" --> G{"What kind of file?"}
  G -- "a PDF, scan or office file" --> G1["Metadata row only.<br/>Its text travels as its digest."]
  G -- "a text file or a digest" --> H["Redact, then chunk"]
  H --> I{"Contains a never term?"}
  I -- "yes" --> DROP["The chunk is dropped"]
  I -- "no" --> UP["Uploaded with its scope"]
  G1 --> UP
  UP --> V["--verify: counts on both sides must match"]
  V --> BK["--backup: the store pulled back into a local SQLite file"]
```

Run `--plan` first: it prints this decision per scope and uploads nothing.

## 18. Reading the shared store

```mermaid
sequenceDiagram
  autonumber
  actor TM as Team member
  actor AN as Anyone without a sign-in
  participant DB as Store (row-level security, forced)
  participant MR as brain_members

  AN->>DB: Any read
  DB-->>AN: Permission error

  TM->>DB: Sign in, then brain_search or a read
  DB->>MR: Which scopes does this user have?
  alt No membership row
    MR-->>DB: none
    DB-->>TM: Zero rows
  else Scopes gtm and templates
    MR-->>DB: gtm, templates
    DB-->>TM: Only rows whose scope is gtm or templates
  end

  TM->>DB: brain_ledger with one entity code
  DB-->>TM: That entity's lines only, never two entities in one result
  Note over DB: Whoever can open the database's dashboard bypasses all of this.<br/>That is why private scopes stay off until the owner confirms who that is.
```

## 19. The data model

The local index, `.index/vault_index.db` and `.index/vectors.db`. Both are rebuilt from the files and can be deleted and built again.

```mermaid
erDiagram
  files ||--o| files_fts : "searched through"
  files ||--o{ edges : "linked by"
  files ||--o{ records : "source of"
  files ||--o| file_map : "embedded as"
  file_map }o--|| chunks : "content key"
  chunks ||--|| vectors : "one vector per chunk"

  files {
    text path PK
    text sha256
    text entity
    text area
    text tier
    text kind
    text doc_date
    text digest_path
    int has_digest
  }
  files_fts {
    text path
    text name
    text purpose
    text digest_text
  }
  edges {
    text src
    text dst
    text rel
  }
  records {
    int id PK
    text kind
    text company
    text ref
    text title
    text due_date
    real amount
    text currency
    text status
    text certainty
    text client
    text source_path
    int source_line
  }
  file_map {
    text path PK
    text sha256
  }
  chunks {
    text sha256 PK
    int ord PK
    text text
  }
  vectors {
    text sha256 PK
    int ord PK
    blob bin
    blob full
    text model
  }
  runs {
    int id PK
    text started
    text mode
    int files_added
    int files_changed
    int records
    int chunks_embedded
  }
```

The shared store. Every table carries a scope, and a member sees only the scopes in their own row.

```mermaid
erDiagram
  brain_documents ||--o{ brain_chunks : "has"
  brain_chunks ||--o| brain_embeddings : "has"
  brain_members }o--o{ brain_documents : "may read, by scope"
  brain_members }o--o{ brain_records : "may read, by scope"

  brain_documents {
    uuid id PK
    scope scope
    text module
    text path
    text sha256
    text company
    text area
    text tier
    bool has_digest
  }
  brain_chunks {
    uuid id PK
    uuid document_id FK
    scope scope
    int ord
    text text
  }
  brain_embeddings {
    uuid chunk_id PK
    scope scope
    bit bin
    halfvec full
    text model
  }
  brain_records {
    uuid id PK
    scope scope
    text kind
    text company
    text ref
    numeric amount
    text currency
    text certainty
    text source_path
  }
  brain_edges {
    uuid id PK
    scope scope
    text src
    text dst
    text rel
  }
  brain_members {
    uuid user_id PK
    scope_array scopes
  }
  brain_sync_runs {
    bigint id PK
    scope scope
    text mode
    text status
    int documents
    int chunks
    int blocked
  }
```

## 20. Several brains, one scheduler

The core stays private on the owner's computer. Other brains live in their own repositories and are reached through links under `Repos/`, never copies.

```mermaid
flowchart TD
  subgraph CORE["Core brain (private, the owner's computer)"]
    C1["Finance and operations"]
    C2["Clients and meetings"]
    C3["daily.md and weekly.md"]
  end

  subgraph LINKED["Linked under Repos/, each its own repository"]
    L1["Go-to-market and sales"]
    L2["Outreach"]
    L3["Design system and templates"]
    L4["One brain per client project"]
  end

  C3 -- "Step 4 and Part F run<br/>schedules/daily.md and weekly.md" --> L1
  C3 --> L2
  C3 --> L3
  C3 --> L4

  L1 -. "five-line result" .-> C3
  L4 -. "five-line result" .-> C3

  L4 --> DH{"brain/DATA_HANDLING.md<br/>says sync: yes?"}
  DH -- "no, confidential,<br/>or the file is missing" --> LOC["Stays on the computer"]
  DH -- "yes" --> STORE["Shared store, scope client:slug"]
  L1 --> STORE2["Shared store, scope gtm"]
```

Who owns which fact across brains: the core owns billing entity, contracts, invoices, payments and profitability; a client brain owns scope, plan, deliverables, decisions and risks of that project; a code repository owns build facts.

## 21. Setup and the first two weeks

```mermaid
flowchart TD
  A["Clone the template"] --> B["python3 scripts/init.py<br/>company, time zone, legal entities"]
  B --> C["Fill 00_Brain/SOURCES.md<br/>where each source is read, and a cheap test"]
  C --> D["Enter what you know<br/>obligations, clients, people, marketing base"]
  D --> E["python3 tools/index/refresh.py --full<br/>python3 tests/test_smoke.py"]
  E --> F["Run daily.md once by hand<br/>and read the result beside the file"]
  F --> G["Schedule the two routines"]
  G --> H["Week one<br/>many not read and unknown answers"]
  H --> I{"For each gap"}
  I -- "a source is not connected" --> J["Connect it"]
  I -- "a document is missing" --> K["Find it and put it in INBOX"]
  J --> L["Second Monday<br/>the answer sheet is mostly Yes and No"]
  K --> L
  L --> O1["Optional: search by meaning"]
  L --> O2["Optional: a shared store for a team"]
```

---

## Drawing your own

Your brain will grow procedures this template does not have: how a quote becomes a contract, how a new client is taken on, how a month is closed with your adviser. Draw them the same way.

- **One diagram answers one question.** Write the question above it.
- **Pick the kind by the question.** Who talks to whom and in which order: a sequence diagram. Which way does it go and where does it branch: a flow chart. Which states can a thing be in: a state diagram. Which tables or files belong together: an entity relationship diagram.
- **Draw the honest branches too:** not read, unknown, refused, waiting for the owner. They are where the routine earns its keep.
- **Name roles, not people.** "Owner", "Bookkeeper", "Client". A diagram is copied further than the file it sits in.
- **Keep it beside what it explains** (a procedure's diagram in that module's folder) and link it from here.
- **The file stays the truth.** When you change a routine, change its diagram in the same edit; Friday's audit lists diagrams that name a step the routine no longer has.

A starting point for a procedure of your own:

````markdown
```mermaid
sequenceDiagram
  autonumber
  actor CL as Client
  participant AG as Agent
  participant FS as Files
  actor OWN as Owner

  CL->>AG: What starts it
  AG->>FS: What is written down, and where
  AG-->>OWN: What is drafted for the owner
  OWN->>CL: What only the owner does
```
````
