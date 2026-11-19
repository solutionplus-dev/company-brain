# Harbour & Pine: a made-up company

Everything in this folder is invented: the company, its two legal entities, its clients, its people, its money. It exists so that every register and routine in the template has a filled-in example, and so the tests have something to index.

Harbour & Pine is a small design and software studio with two legal entities that must never be mixed:

| Code | Entity | Folder |
|---|---|---|
| `DE` | Harbour & Pine GmbH (Hamburg) | `Entity_DE/` |
| `UK` | Harbour & Pine Ltd (Leeds) | `Entity_UK/` |

Try it:

```bash
BRAIN_ROOT=examples/harbour-pine python3 tools/index/refresh.py --root examples/harbour-pine --full
BRAIN_ROOT=examples/harbour-pine python3 tools/index/query.py --root examples/harbour-pine "bookshop ordering app"
BRAIN_ROOT=examples/harbour-pine python3 tools/index/query.py --root examples/harbour-pine --records kind=deadline
```
