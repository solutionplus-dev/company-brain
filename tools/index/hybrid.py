#!/usr/bin/env python3
"""Hybrid search over the brain's index: exact words and meaning, fused, with a reason for every hit.

Four ranked lists of files:
  1. keywords in the catalogue   files_fts in the index database: path, name, purpose and the first part
                                 of the text.
  2. keywords in the file name   the same table, name only: the file named for a topic is its home.
  3. keywords in the passages    chunks_fts in the vectors database: the whole text of every embedded file,
                                 cut into passages. Finds a number or a code deep inside a long document.
  4. meaning                     the embedding search (embed/embed.py), when it is installed.

The lists are fused by weighted reciprocal rank. `alpha` is the weight of meaning against keywords
(0 = keywords only, 1 = meaning only). It is chosen from the question unless given:
  a number, a code or a quoted phrase in the question   0.25  (and when the exact text is found, the
                                                              model is not started at all)
  one or two words (a name lookup)                      0.40
  a question in plain words                             0.50

After fusion: an exact file name stays first; a digest counts for its original; logs of a past month or
year, history copies and the search's own test files rank below the document that is the home of a fact.

Every hit says why it is there (`why`) and how far to trust it (`confidence`: strong, fair, weak).
When nothing is better than weak the search says so: the right answer may be "not in the brain".

Standard library only. Read-only, except ensure_passages(), which the refresh calls.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sqlite3
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EMBED_FILE = HERE / "embed" / "embed.py"
RRF_K = 60
DEPTH = 60                      # how deep each list is read before fusion, whatever the output limit
# how the keyword weight is shared between its lists (the catalogue takes over when there are no passages)
SHARE = {"file": 0.55, "passage": 0.45}
NAME_WEIGHT = 1.0               # a file named for the topic counts about as much as a first place elsewhere
NAME_MIN = 0.3                  # below this the name match is only noted, not counted
BM25_FILES = (2.0, 6.0, 3.0, 1.0, 0.3)   # path, name, purpose, text, entity
TIER_FACTOR = {"current": 1.0, "month": 0.9, "year": 0.8, "archive": 0.7}
# Not the home of a fact: copies kept for history, and the files the search is tested with.
DEMOTE = (("/history/", 0.5), ("/EVALUATIONS/", 0.4), ("eval_queries", 0.4), ("/retired/", 0.6),
          ("_HISTORY.md", 0.7))
LABEL = {"all": "every term", "exact": "the exact number, code or phrase", "any": "some terms"}
NEAR_TOP = 10                   # a place in a list counts as agreement only this near its top
NEAR_SOME = 3                   # ... and only this near when just some of the terms matched
MEANING_FLOOR = 0.70            # best-passage similarity below this is off topic (measured: questions the
                                # brain can answer score 0.74 and more, unrelated ones 0.67 and less)

STOP = set("""
a an and are as at be by can did do does for from had has have how i in is it its me my of on or our
shall should that the their there these this those to was we were what when where which who whom whose
why will with would you your about any per into than then them they us up
der die das den dem des ein eine einen einem einer eines und oder ist sind war waren wie was wer wo wann
warum welche welcher welches welchen wir ihr sie es ich du mit von vom zu zum zur im in am an auf aus bei
für fuer nach über ueber unter um als auch nicht noch hat haben wird werden kann können koennen dass
""".split())

WORD = re.compile(r"[^\W_]+", re.UNICODE)
RAW_TOKEN = re.compile(r'"[^"]+"|\S+')


# ---------------------------------------------------------------- the question

def _stem(word: str) -> str:
    """A light stem for prefix matching: plural endings only."""
    w = word
    if len(w) >= 6 and w.endswith("ies"):
        return w[:-3]
    if len(w) >= 7 and w.endswith("en"):
        return w[:-2]
    if len(w) >= 5 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _is_identifier(token: str, pieces: list[str]) -> bool:
    if any(ch.isdigit() for ch in token) and sum(len(p) for p in pieces) >= 3:
        return True
    return bool(re.fullmatch(r"[A-Z]{2,}(?:[-_/.][A-Z0-9]+)+", token))


def analyse(question: str, alpha: float | None = None) -> dict:
    """Split a question into what the keyword side must match. -> dict (terms, kind, alpha)."""
    terms: list[dict] = []
    dropped: list[str] = []
    for raw in RAW_TOKEN.findall(question.strip()):
        quoted = len(raw) > 2 and raw.startswith('"') and raw.endswith('"')
        token = raw.strip('"') if quoted else raw.strip("?!.,;:()[]{}'`")
        pieces = [p.lower() for p in WORD.findall(token)]
        if not pieces:
            continue
        if quoted:
            terms.append({"text": token, "expr": '"%s"' % " ".join(pieces), "kind": "phrase"})
        elif _is_identifier(token, pieces):
            terms.append({"text": token, "expr": '"%s"' % " ".join(pieces), "kind": "identifier"})
        elif len(pieces) > 1:
            terms.append({"text": token, "expr": '"%s"' % " ".join(pieces), "kind": "word"})
        elif pieces[0] in STOP:
            dropped.append(pieces[0])
        else:
            stem = _stem(pieces[0])
            expr = ('"%s"*' % stem) if len(stem) >= 4 else ('"%s"' % pieces[0])
            terms.append({"text": token, "expr": expr, "kind": "word"})
    if not terms:  # a question made of small words only: match them as written
        terms = [{"text": w, "expr": '"%s"' % w, "kind": "word"} for w in dropped]
    seen, uniq = set(), []
    for t in terms:
        if t["expr"] not in seen:
            seen.add(t["expr"])
            uniq.append(t)
    exact = [t for t in uniq if t["kind"] in ("identifier", "phrase")]
    if exact:
        kind, auto = "exact", 0.25
    elif len(uniq) <= 2:
        kind, auto = "short", 0.40
    else:
        kind, auto = "question", 0.50
    a = auto if alpha is None else max(0.0, min(1.0, float(alpha)))
    return {"raw": question.strip(), "terms": uniq, "exact_terms": exact, "kind": kind, "alpha": a,
            "alpha_auto": alpha is None}


def match_exprs(an: dict) -> list[tuple[str, str]]:
    """The keyword passes, strictest first: every term; every number, code and quoted phrase; any term.
    -> [(label, expression)] without repeats."""
    exprs = [t["expr"] for t in an["terms"]]
    exact = [t["expr"] for t in an["exact_terms"]]
    passes = [("all", " AND ".join(exprs))]
    if exact and len(exact) < len(exprs):
        passes.append(("exact", " AND ".join(exact)))
    passes.append(("any", " OR ".join(exprs)))
    out, seen = [], set()
    for label, expr in passes:
        if expr and expr not in seen:
            seen.add(expr)
            out.append((label, expr))
    return out


# ---------------------------------------------------------------- signal 1: catalogue

def keyword_files(conn: sqlite3.Connection, an: dict, frag: str, fparams: list, ext: str,
                  depth: int = DEPTH) -> list[dict]:
    """Catalogue rows, best first: files that hold every term, then files that hold some."""
    passes = match_exprs(an)
    if not passes:
        return []
    weights = ", ".join(str(w) for w in BM25_FILES)
    sql = (f"SELECT f.path, f.name, f.entity, f.kind, f.year_month, f.purpose, f.certainty, f.size, {ext}, "
           f"snippet(files_fts, 3, '[', ']', '…', 14) AS snippet, bm25(files_fts, {weights}) AS rank "
           "FROM files_fts JOIN files f ON f.path = files_fts.path WHERE files_fts MATCH ?" + frag
           + " ORDER BY rank LIMIT ?")
    out: list[dict] = []
    seen: set[str] = set()
    for label, expr in passes:
        if len(out) >= depth:
            break
        try:
            rows = conn.execute(sql, [expr] + fparams + [depth]).fetchall()
        except sqlite3.OperationalError:
            rows = []
        for r in rows:
            if r["path"] not in seen:
                seen.add(r["path"])
                d = dict(r)
                d["kw"] = label
                out.append(d)
    return out[:depth]


NAME_NOISE = {"md", "txt", "pdf", "json", "csv", "html", "docx", "xlsx", "py", "js", "sh", "digest", "eml"}


def keyword_names(conn: sqlite3.Connection, an: dict, frag: str, fparams: list, depth: int = 30) -> list[dict]:
    """Files whose name holds terms of the question, best first. `quality` (0 to 1) is high when the name
    is little more than the question's own words: the file named for a topic is the home of that topic.
    Scored here, not by the database: its ranking favours files that have no text."""
    terms = an["terms"]
    if not terms:
        return []
    sql = ("SELECT f.path, f.name, f.kind, f.tier FROM files_fts JOIN files f ON f.path = files_fts.path "
           "WHERE files_fts MATCH ?" + frag + " LIMIT 600")
    try:
        rows = conn.execute(sql, ["{name} : (" + " OR ".join(t["expr"] for t in terms) + ")"] + fparams).fetchall()
    except sqlite3.OperationalError:
        return []
    needles = []
    for t in terms:
        pieces = WORD.findall(t["expr"].lower())
        needles.append((pieces, t["expr"].endswith("*")))
    out = []
    for r in rows:
        toks = [w.lower() for w in WORD.findall(r["name"] or "")]
        body = [w for w in toks if w not in NAME_NOISE] or toks
        used: set[int] = set()
        matched = 0
        for pieces, prefix in needles:
            hit = None
            if len(pieces) == 1:
                hit = next((i for i, w in enumerate(body) if (w.startswith(pieces[0]) if prefix else w == pieces[0])), None)
                span = [hit] if hit is not None else []
            else:
                n = len(pieces)
                hit = next((i for i in range(len(body) - n + 1) if body[i:i + n] == pieces), None)
                span = list(range(hit, hit + n)) if hit is not None else []
            if span:
                matched += 1
                used.update(span)
        if not matched:
            continue
        coverage = len(used) / max(1, len(body))
        quality = coverage * (0.5 + 0.5 * matched / len(needles))
        if r["kind"] in ("file", "image", "media"):     # code and pictures are rarely the home of a fact
            quality *= 0.5
        quality *= TIER_FACTOR.get(r["tier"] or "current", 1.0)
        out.append({"path": r["path"], "kw": "name", "quality": round(quality, 3)})
    out.sort(key=lambda h: (-h["quality"], len(h["path"]), h["path"]))
    return out[:depth]


# ---------------------------------------------------------------- signal 2: passages

def vectors_db_for(index_db: Path) -> Path:
    return Path(index_db).parent / "vectors.db"


def _chunk_signature(con: sqlite3.Connection) -> str:
    n, top, chars = con.execute("SELECT count(*), coalesce(max(rowid), 0), coalesce(sum(n_chars), 0) "
                                "FROM chunks").fetchone()
    return f"{n}:{top}:{chars}"


def ensure_passages(vectors_db: Path) -> dict:
    """Build or refresh the full-text index over the passages (chunks_fts). Called by the refresh.
    Rebuilds only when the passages changed. -> {'passages': n, 'rebuilt': bool, 'seconds': s}"""
    vectors_db = Path(vectors_db)
    if not vectors_db.is_file():
        return {"passages": 0, "rebuilt": False, "note": "no vectors database"}
    t0 = time.time()
    con = sqlite3.connect(str(vectors_db), timeout=120)
    try:
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='chunks'").fetchone() is None:
            return {"passages": 0, "rebuilt": False, "note": "no passages yet"}
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
                    "text, content='chunks', content_rowid='rowid', tokenize='unicode61')")
        con.execute("CREATE TABLE IF NOT EXISTS passages_meta (key TEXT PRIMARY KEY, value TEXT)")
        sig = _chunk_signature(con)
        old = con.execute("SELECT value FROM passages_meta WHERE key='signature'").fetchone()
        rebuilt = False
        if not old or old[0] != sig:
            con.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
            con.execute("INSERT OR REPLACE INTO passages_meta (key, value) VALUES ('signature', ?)", (sig,))
            con.commit()
            rebuilt = True
        n = int(sig.split(":")[0])
        return {"passages": n, "rebuilt": rebuilt, "seconds": round(time.time() - t0, 2)}
    finally:
        con.close()


def keyword_passages(vectors_db: Path, an: dict, depth: int = DEPTH) -> tuple[list[dict] | None, str]:
    """Passages that hold the terms, one hit per file, best first. None when there is no passage index.
    -> (hits, note). A hit: {path, passage, kw}"""
    vectors_db = Path(vectors_db)
    if not vectors_db.is_file():
        return None, "no passage index"
    try:
        con = sqlite3.connect(f"file:{vectors_db}?mode=ro", uri=True, timeout=5)
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='chunks_fts'").fetchone() is None:
            con.close()
            return None, "no passage index (the next refresh builds it)"
    except sqlite3.Error as e:
        return None, f"passage index not readable ({type(e).__name__})"
    sql = ("SELECT c.sha256, snippet(chunks_fts, 0, '[', ']', '…', 24) FROM chunks_fts "
           "JOIN chunks c ON c.rowid = chunks_fts.rowid WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?")
    out: list[dict] = []
    seen: set[str] = set()
    try:
        for label, expr in match_exprs(an):
            if len(out) >= depth:
                break
            for sha, snip in con.execute(sql, (expr, depth * 3)).fetchall():
                for (path,) in con.execute("SELECT path FROM file_map WHERE sha256 = ? ORDER BY path", (sha,)):
                    if path not in seen:
                        seen.add(path)
                        out.append({"path": path, "passage": snip, "kw": label})
                if len(out) >= depth * 2:
                    break
    except sqlite3.Error as e:
        con.close()
        return None, f"passage search failed ({type(e).__name__})"
    con.close()
    return out, "ok"


# ---------------------------------------------------------------- signal 3: meaning

def meaning_hits(index_db: Path, question: str, k: int = DEPTH, embed_file: Path | None = None
                 ) -> tuple[list[dict] | None, str]:
    """Hits from embed/embed.py search(), or None with the reason when meaning is not available."""
    embed_file = embed_file or EMBED_FILE
    if not Path(embed_file).is_file():
        return None, "not installed"
    try:
        spec = importlib.util.spec_from_file_location("_index_embed_query", embed_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, "search", None)
        if not callable(fn):
            return None, "not installed"
        hits = fn(str(index_db), question, k) or []
    except Exception as e:  # noqa: BLE001 - keywords still answer without the model
        if os.environ.get("INDEX_DEBUG"):
            print(f"meaning search skipped: {type(e).__name__}: {e}", file=sys.stderr)
        if "setup.sh" in str(e):
            return None, "not set up (tools/index/embed/setup.sh); keywords answer alone"
        if "another brain" in str(e):
            return None, "busy (another search has the model loaded); keywords answer alone"
        return None, f"not available ({type(e).__name__})"
    out = []
    for h in hits:
        if isinstance(h, dict):
            if h.get("path"):
                out.append({"path": str(h["path"]), "score": h.get("score"), "passage": h.get("text") or ""})
        elif isinstance(h, (list, tuple)):
            if h and h[0]:
                out.append({"path": str(h[0]), "score": None, "passage": ""})
        elif h:
            out.append({"path": str(h), "score": None, "passage": ""})
    return out, "ok"


# ---------------------------------------------------------------- fusion

def _short(text: str | None, n: int = 320) -> str | None:
    if not text:
        return None
    t = re.sub(r"\s+", " ", text).strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _prior(path: str, tier: str | None) -> float:
    f = TIER_FACTOR.get(tier or "current", 1.0)
    for needle, factor in DEMOTE:
        if needle in path:
            f *= factor
    return f


def search(conn: sqlite3.Connection, index_db: Path | None, question: str, limit: int = 20,
           frag: str = "", fparams: list | None = None, ext: str = "NULL AS area, NULL AS tier",
           alpha: float | None = None, meaning: str = "auto", vec_hits: list | None = None,
           embed_file: Path | None = None) -> tuple[list[dict], dict]:
    """The hybrid search. -> (rows, info).

    frag / fparams   extra WHERE clauses on files (alias f) and their parameters
    meaning          'auto' (skip the model when an exact number, code or phrase is found by keywords),
                     'on' (always ask it), 'off' (keywords only)
    vec_hits         a ready meaning list (paths or dicts); the model is then not asked
    """
    t0 = time.time()
    fparams = list(fparams or [])
    an = analyse(question, alpha)
    info: dict = {"question": an["raw"], "kind": an["kind"], "alpha": an["alpha"],
                  "terms": [t["text"] for t in an["terms"]]}
    if not an["terms"]:
        info.update({"verdict": "empty question", "seconds": 0.0})
        return [], info

    cols = (f"f.path, f.name, f.entity, f.kind, f.year_month, f.purpose, f.certainty, f.size, {ext}")
    q = an["raw"]
    exact = [dict(r) for r in conn.execute(
        f"SELECT {cols} FROM files f WHERE (f.name = ? OR f.path = ?)" + frag, [q, q] + fparams)]

    # meaning starts first when it will certainly be used: the model loads while the keywords are read
    vec: list[dict] | None = None
    vec_note = "off"
    worker = None
    box: dict = {}
    want_model = meaning != "off" and vec_hits is None and index_db is not None and an["alpha"] > 0

    def _ask_model():
        box["hits"], box["note"] = meaning_hits(Path(index_db), q, DEPTH, embed_file)

    if want_model and (meaning == "on" or an["kind"] != "exact"):
        worker = threading.Thread(target=_ask_model, daemon=True)
        worker.start()

    kfiles = keyword_files(conn, an, frag, fparams, ext)
    knames = keyword_names(conn, an, frag, fparams)
    kpass, pass_note = (None, "no index database")
    if index_db is not None:
        kpass, pass_note = keyword_passages(vectors_db_for(Path(index_db)), an)
    info["passages"] = pass_note

    holds = ("all", "exact")          # passes in which every number, code and phrase of the question matched
    exact_found = bool(an["exact_terms"]) and (any(r["kw"] in holds for r in kfiles)
                                               or any(h["kw"] in holds for h in (kpass or [])))
    if vec_hits is not None:
        vec = [h if isinstance(h, dict) else {"path": str(h), "score": None, "passage": ""} for h in vec_hits]
        vec_note = "given"
    elif worker is not None:
        worker.join()
        vec, vec_note = box.get("hits"), box.get("note", "not available")
    elif want_model and not exact_found:
        _ask_model()                     # an identifier the keywords did not find: let meaning try
        vec, vec_note = box.get("hits"), box.get("note", "not available")
    elif want_model:
        vec_note = "skipped (the exact text was found by keywords)"
    info["meaning"] = vec_note

    # a digest counts for its original
    def canon(path: str) -> str:
        if path.endswith(".digest.md"):
            orig = path[: -len(".digest.md")]
            if orig in known or conn.execute("SELECT 1 FROM files WHERE path = ?", (orig,)).fetchone():
                known.add(orig)
                return orig
        return path

    known: set[str] = set()
    lists: dict[str, list[dict]] = {"file": [], "name": [], "passage": [], "meaning": []}
    for name, src in (("file", kfiles), ("name", knames), ("passage", kpass or []), ("meaning", vec or [])):
        seen: set[str] = set()
        for h in src:
            p = canon(h["path"])
            if p not in seen:
                seen.add(p)
                lists[name].append(dict(h, path=p, moved=(p != h["path"])))

    a = an["alpha"]
    share = dict(SHARE)
    if kpass is None:                    # no passage index: the catalogue takes its share
        share["file"] += share.pop("passage")
    kw_weight = 2.0 if not lists["meaning"] else 2 * (1 - a)   # keywords only: nothing to balance against
    w = {name: kw_weight * part for name, part in share.items()}
    w["meaning"] = 2 * a
    score: dict[str, float] = {}
    ranks: dict[str, dict] = {}
    for name in ("file", "passage", "meaning"):
        for i, h in enumerate(lists[name], start=1):
            p = h["path"]
            score[p] = score.get(p, 0.0) + w[name] / (RRF_K + i)
            ranks.setdefault(p, {})[name] = (i, h)
    # the name is not a fourth vote of equal kind: it lifts a file that another list also found
    for i, h in enumerate(lists["name"], start=1):
        p = h["path"]
        if h["quality"] >= NAME_MIN and (p in score or h["quality"] >= 0.75):
            score[p] = score.get(p, 0.0) + NAME_WEIGHT * h["quality"] / (RRF_K + 1)
            ranks.setdefault(p, {})["name"] = (i, h)

    # catalogue rows for every candidate, with the caller's filters applied
    rows: dict[str, dict] = {r["path"]: dict(r, snippet=None) for r in exact}
    for h in lists["file"]:
        if not h["moved"]:
            rows.setdefault(h["path"], {k: v for k, v in h.items() if k not in ("kw", "rank", "moved")})
    missing = [p for p in score if p not in rows]
    for i in range(0, len(missing), 400):
        part = missing[i:i + 400]
        marks = ",".join("?" * len(part))
        for r in conn.execute(f"SELECT {cols} FROM files f WHERE f.path IN ({marks})" + frag, part + fparams):
            rows[r["path"]] = dict(r, snippet=None)
    exact_paths = {r["path"] for r in exact}
    for p in exact_paths:
        score.setdefault(p, 0.0)

    final: list[tuple[float, str]] = []
    for p, s in score.items():
        if p in rows:
            final.append((s * _prior(p, rows[p].get("tier")), p))
    pinned = set()
    if an["exact_terms"]:             # the exact number, code or phrase beats any amount of similar wording
        pinned = {p for p, rk in ranks.items()
                  if any(n in rk and rk[n][1]["kw"] in holds for n in ("file", "passage"))}
    final.sort(key=lambda x: (0 if x[1] in exact_paths else 1 if x[1] in pinned else 2, -x[0], x[1]))

    out: list[dict] = []
    for s, p in final[:limit]:
        r = rows[p]
        rk = ranks.get(p, {})
        why = []
        if p in exact_paths:
            why.append("exact file name")
        if "file" in rk:
            i, h = rk["file"]
            why.append(f"keywords #{i} ({LABEL[h['kw']]})")
        if "name" in rk:
            why.append(f"file name ({rk['name'][1]['quality']:.2f})")
        if "passage" in rk:
            i, h = rk["passage"]
            why.append(f"passage #{i} ({LABEL[h['kw']]})")
        if "meaning" in rk:
            i, h = rk["meaning"]
            why.append(f"meaning #{i}" + (f" ({h['score']:.2f})" if isinstance(h.get("score"), (int, float)) else ""))
        def agrees(name: str) -> bool:
            if name not in rk:
                return False
            place, h = rk[name]
            if name == "meaning":
                sc = h.get("score")
                return place <= NEAR_TOP and (not isinstance(sc, (int, float)) or sc >= MEANING_FLOOR)
            return place <= (NEAR_TOP if h["kw"] in holds else NEAR_SOME)

        near = sum(1 for name in ("file", "passage", "meaning") if agrees(name))
        named = "name" in rk and rk["name"][1]["quality"] >= 0.6
        kw_all = any(name in rk and rk[name][1]["kw"] == "all" and rk[name][0] <= NEAR_TOP
                     for name in ("file", "passage"))
        if p in exact_paths or p in pinned or near == 3 or (named and near >= 1):
            conf = "strong"
        elif near >= 2 or kw_all or named:
            conf = "fair"
        else:
            conf = "weak"
        passage = None
        if "passage" in rk:
            passage = rk["passage"][1].get("passage")
        if not passage and "meaning" in rk:
            passage = rk["meaning"][1].get("passage")
        r = dict(r)
        r["snippet"] = _short(passage) or _short(rk["file"][1].get("snippet") if "file" in rk else None)
        r["score"] = round(s, 5)
        r["why"] = ", ".join(why)
        r["confidence"] = conf
        out.append(r)

    best = next((c for c in ("strong", "fair", "weak") if any(r["confidence"] == c for r in out)), None)
    top_sim = next((h.get("score") for h in lists["meaning"] if isinstance(h.get("score"), (int, float))), None)
    if top_sim is not None:
        info["meaning_top"] = round(float(top_sim), 3)
        if top_sim < MEANING_FLOOR and best == "fair" and not any(
                any(n in ranks.get(r["path"], {}) and ranks[r["path"]][n][1]["kw"] in holds for n in ("file", "passage"))
                for r in out[:3]):
            best = "weak"                # nothing reads like the question and no top hit holds all its words
    if not out:
        info["verdict"] = "nothing found"
    elif best == "weak":
        info["verdict"] = ("weak matches only: the brain may not hold this. Open a result before relying on it, "
                           "or answer that it was not found.")
    else:
        info["verdict"] = "found"
    info["mode"] = ("keywords + meaning" if lists["meaning"] else "keywords only")
    info["seconds"] = round(time.time() - t0, 2)
    return out, info
