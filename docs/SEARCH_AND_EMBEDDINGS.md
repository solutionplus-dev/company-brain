# Search and embeddings

As pictures: `docs/DIAGRAMS.md`, diagrams 15 (building the index), 16 (a search) and 19 (the data model).

## The index (always on)

`python3 tools/index/refresh.py` walks the folders, hashes each file, reads text and digests, and writes `.index/vault_index.db`: a catalogue with full-text search, plus business records read from the registers. Python standard library and SQLite; nothing to install.

```bash
scripts/brain ask "insurance renewal"
scripts/brain ask --area clients "launch date"
scripts/brain records kind=deadline company=DE
scripts/brain records kind=ledger_line company=UK
scripts/brain file "01_Clients/<slug>/STATUS.md"
```

PDFs, scans and office files are found through the `.digest.md` an agent writes beside them when filing: a short reading of the document in plain text. The digest is searchable; the original stays the truth.

## How a search is put together

One model of "similar text" is not enough for a company's files. Ask for an invoice number, a decision id or a paragraph of a contract and a search by meaning brings back documents that talk about similar things, not the one that holds the number. Keywords alone miss the paraphrase and the other language. So `scripts/brain ask` reads four ranked lists and fuses them (`tools/index/hybrid.py`):

| List | What it is good at |
|---|---|
| keywords in the catalogue (path, name, purpose, the start of the text) | names, purposes, short files |
| keywords in the file name | the home document of a topic: `DEADLINES.md` for a question about deadlines |
| keywords in the passages (the whole text, cut into pieces; present once embeddings are set up) | a number or a code deep inside a long document |
| meaning (optional, below) | paraphrase, the other language |

- **The balance is chosen from the question.** `alpha` is the weight of meaning against keywords (0 = keywords only, 1 = meaning only): 0.25 when the question holds a number, a code or a "quoted phrase", 0.40 for one or two words, 0.50 for a question in plain words. `--alpha 0.7` overrides it. There is no single right value: a register of codes wants keywords, a folder of meeting notes wants meaning, and a company has both.
- **Exact text wins.** A file that holds every number, code and quoted phrase of the question ranks above anything that merely reads alike, and the model is not even started. Small words of a question ("which", "the", "der", "wie") are dropped; plurals match by prefix.
- **The home of a fact outranks its echoes.** A digest counts for its original. Logs of a closed month or year, history copies and the search's own test file rank below the document the fact lives in.
- **Every hit says why it is there and how far to trust it.** `why` names the lists and the places (`keywords #1 (every term), passage #3, meaning #2 (0.78)`); `confidence` is strong, fair or weak. When nothing is better than weak the search prints that the brain may not hold the answer, and an agent is expected to say "not found" instead of answering from the nearest text.
- **No re-ranking model.** A third model that re-reads the candidates made results worse on the brain this template was drawn from, and it would be a second model in memory. Measure on your own files before adding one.

```bash
scripts/brain ask "where is DEC-2030-003 decided"          # exact: answers at once, no model
scripts/brain ask "which deadlines are coming up"           # plain words
scripts/brain ask "fixed price contract" --json --explain   # for agents: verdict, alpha and the reason for each hit
```

### For agents: the passages, not the files

An agent that gets ten paths back opens ten files to find the two paragraphs it needs. `scripts/brain find "<question>"` returns those paragraphs instead: for the best hits only, the passage that matched, the file it is read from and its line range, and the business records whose reference is named in the question.

```bash
scripts/brain find "where is DEC-2030-003 decided"
scripts/brain find "which deadlines are coming up" --json --top 3 --budget 3000
```

`--budget` caps the passage text in characters (6,000, shared between the files) and `--top` the number of files (5). A passage is placed by exact match or by a line that occurs once in the file; when it cannot be placed the result says so instead of giving a wrong range. Passages come from the passage store, so they are redacted the way the embedder stored them; a hit outside that store carries its short snippet. The agent answers from those lines, cites the path, and opens a whole file only when the passage does not answer.

What changed when the brain this template was drawn from moved from "every word must match, in the first part of each file, fused with meaning" to the above (its own numbers, about 5,800 files; `scripts/brain check` gives you yours):

| Test | Before | After |
|---|---|---|
| 15 standing questions, expected file in the first five | 10 | 15 |
| 24 fresh questions, not used for tuning | 19 | 23 |
| 29 codes that sit deep inside long documents | 10 | 26 (the other three are archived; the search says so and `--all` shows them) |
| A question with a code in it | about 3 s | about 0.1 s |

Without embeddings there are no passages yet, so the keyword side reads the first 16,384 characters of each file; the other rules apply all the same.

## Search by meaning (optional, Apple silicon)

```bash
tools/index/embed/setup.sh                      # virtual environment and the model, about 1.1 GB
tools/index/.venv/bin/python tools/index/embed/embed.py pending
scripts/brain ask "who still owes us money"     # now keyword and meaning, fused
```

How it is built:

- Text is cut into chunks of about 1,200 characters with overlap, **redacted first** (phone numbers, private e-mail addresses, ID and account numbers), and embedded with a small multilingual model that runs on the laptop. No text leaves the computer.
- Each chunk is stored twice in `.index/vectors.db`: the **sign bit** of each of the 768 dimensions (96 bytes), and the full vector as 8-bit integers (about 770 bytes).
- A query scans the 96-byte codes first, keeps the best 300, and re-ranks those exactly. Keyword and meaning results are fused by weighted reciprocal rank (above).
- The model lives in a short-lived process and is gone when the search ends. A question asked before is answered from `.index/query_cache.db` (a hash of the question and its vector, never its words) without loading the model.
- Files matched by `.brainignore`, credentials, identity documents and guarded client folders are never embedded.

What we measured on the brain this template was drawn from (about 45,000 chunks in two languages; `tools/index/embed/evaluate.py` reproduces it on yours):

| Measure | Result |
|---|---|
| The exact top 10 found inside the 300-candidate shortlist | 97 % |
| 8-bit stored vector against the full-precision one (cosine) | 0.9998 |
| Query: embed about 10 ms, shortlist and re-rank about 5 ms, exact scan about 33 ms | |
| A question and its translation into the other language share top-10 results | 18 % |

The last line is the honest one: the small model finds well within a language and weakly across languages. Questions in the smaller language bring back documents in the larger one; the reverse is rare. Keyword search and digests written in both languages cover part of that gap. Measure before you rely on it.

The model weights are quantised to 4 bits (the smallest published build); the 1-bit part is how the *vectors* are stored and searched, not the model.
