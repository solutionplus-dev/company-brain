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

## Search by meaning (optional, Apple silicon)

```bash
tools/index/embed/setup.sh                      # virtual environment and the model, about 1.1 GB
tools/index/.venv/bin/python tools/index/embed/embed.py pending
scripts/brain ask "who still owes us money"     # now keyword and meaning, fused
```

How it is built:

- Text is cut into chunks of about 1,200 characters with overlap, **redacted first** (phone numbers, private e-mail addresses, ID and account numbers), and embedded with a small multilingual model that runs on the laptop. No text leaves the computer.
- Each chunk is stored twice in `.index/vectors.db`: the **sign bit** of each of the 768 dimensions (96 bytes), and the full vector as 8-bit integers (about 770 bytes).
- A query scans the 96-byte codes first, keeps the best 300, and re-ranks those exactly. Keyword and meaning results are fused by reciprocal rank.
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
