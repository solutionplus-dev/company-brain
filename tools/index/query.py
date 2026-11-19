#!/usr/bin/env python3
"""Query the vault catalog (.index/vault_index.db). Read-only. Stdlib only.

  query.py [--json] [--limit N] [--entity E] [--area A] [--tier T] [--all] [--no-embed] TERMS
      Full-text search of files. Tier `archive` is hidden unless --all or --tier archive is given.
      If tools/index/embed/embed.py exposes search(index_db_path, query, k), its hits are fused with the full-text
      ranks (reciprocal rank fusion, k=60). If it does not, or returns nothing, the result is full-text only.
  query.py --records [--json] [--limit N] kind=invoice status=open company=DE due_before=2030-12-01 [WORDS]
      Records (the `records` table, filled by the importers). Amounts are shown as written, never summed.
      Keys: kind, company, status, ref, currency, certainty, client (comma lists allowed: kind=invoice,expense);
      counterparty (contains); due_before, due_after, date_before, date_after (ISO dates; due_before is strictly
      before); amount_min, amount_max. Words without = match title, counterparty, ref or extra.
  query.py --info PATH        one file's row and its edges
  query.py --stats            counts per entity, area, tier and record kind
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ in the vault

TOKEN = re.compile(r"[^\s\"']+")
HERE = Path(__file__).resolve().parent
EMBED_FILE = HERE / "embed" / "embed.py"
RRF_K = 60
TIERS = ("current", "month", "year", "archive")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import brainconfig  # noqa: E402

AREAS = tuple(sorted(set(brainconfig.area_by_top().values()) | {"system", "other"}))
RECORD_EQ = {"kind": "kind", "company": "company", "status": "status", "ref": "ref", "currency": "currency",
             "certainty": "certainty", "client": "client"}
RECORD_LIKE = {"counterparty": "counterparty"}
RECORD_DATE = {"due_before": ("due_date", "<"), "due_after": ("due_date", ">="),
               "date_before": ("date", "<"), "date_after": ("date", ">=")}
RECORD_NUM = {"amount_min": (">=",), "amount_max": ("<=",)}
RECORD_KEYS = set(RECORD_EQ) | set(RECORD_LIKE) | set(RECORD_DATE) | set(RECORD_NUM)
RECORD_COLS = ("id, kind, company, ref, title, date, due_date, amount, amount_text, currency, counterparty, "
               "status, certainty, client, source_path, source_line")


def fts_query(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    if any(op in raw.upper().split() for op in ("AND", "OR", "NOT")) or '"' in raw:
        return raw
    parts = TOKEN.findall(raw)
    out = []
    for p in parts:
        if "." in p and not p.startswith("."):
            out.append(" AND ".join(f'"{bit}"' for bit in p.replace(".", " ").split() if bit))
        else:
            out.append(f'"{p}"')
    return " AND ".join(out)


def connect(db: Path) -> sqlite3.Connection:
    if not db.is_file():
        sys.exit(f"index missing: {db} (run: python3 tools/index/refresh.py --full)")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def stamp(root: Path, kind: str, detail: str) -> None:
    """Mark that the agent used the catalog. An editor hook may use this stamp to allow a plain text search afterwards."""
    path = root / ".index" / "last_query"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "kind": kind,
                "detail": (detail or "")[:240],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def file_filter(conn: sqlite3.Connection, entity, area, tier, include_all) -> tuple[str, list]:
    """Extra WHERE clauses for files (alias f). Default hides tier archive."""
    cols = table_columns(conn, "files")
    clauses, params = [], []
    if entity:
        clauses.append("f.entity = ?")
        params.append(entity)
    if area:
        if "area" not in cols:
            sys.exit("this index has no area column yet: run tools/index/migrate.py")
        clauses.append("f.area = ?")
        params.append(area)
    if tier:
        if "tier" not in cols:
            sys.exit("this index has no tier column yet: run tools/index/migrate.py")
        clauses.append("f.tier = ?")
        params.append(tier)
    elif not include_all and "tier" in cols:
        clauses.append("COALESCE(f.tier, 'current') <> 'archive'")
    return "".join(f" AND {c}" for c in clauses), params


def _ext_cols(conn: sqlite3.Connection) -> str:
    return "f.area, f.tier" if "area" in table_columns(conn, "files") else "NULL AS area, NULL AS tier"


def fuse(conn, fts: list[dict], vec_paths: list[str], frag: str, fparams: list, limit: int, ext: str) -> list[dict]:
    """Reciprocal rank fusion of the full-text list and the embedding list. Exact name/path hits stay first."""
    score: dict[str, float] = {}
    rows: dict[str, dict] = {}
    for i, r in enumerate(fts):
        score[r["path"]] = score.get(r["path"], 0.0) + 1.0 / (RRF_K + i + 1)
        rows[r["path"]] = r
    for i, p in enumerate(vec_paths):
        score[p] = score.get(p, 0.0) + 1.0 / (RRF_K + i + 1)
        if p not in rows:
            row = conn.execute(
                f"SELECT f.path, f.name, f.entity, f.kind, f.year_month, f.purpose, f.certainty, f.size, {ext}, "
                f"NULL AS snippet, NULL AS rank FROM files f WHERE f.path = ?{frag}",
                [p] + fparams,
            ).fetchone()
            if row:
                rows[p] = dict(row)
    order = sorted((p for p in score if p in rows),
                   key=lambda p: (0 if rows[p].get("rank") == -1e9 else 1, -score[p]))
    out = []
    for p in order[:limit]:
        r = rows[p]
        r["score"] = round(score[p], 5)
        out.append(r)
    return out


def cmd_search(conn: sqlite3.Connection, q: str, limit: int, entity: str | None = None, area: str | None = None,
               tier: str | None = None, include_all: bool = False, vec_paths: list[str] | None = None) -> list[dict]:
    match = fts_query(q)
    if not match:
        sys.exit("empty query")
    frag, fparams = file_filter(conn, entity, area, tier, include_all)
    ext = _ext_cols(conn)
    exact_sql = (f"SELECT f.path, f.name, f.entity, f.kind, f.year_month, f.purpose, f.certainty, "
                 f"f.size, {ext}, NULL AS snippet, -1e9 AS rank FROM files f WHERE (f.name = ? OR f.path = ?)") + frag
    exact = [dict(r) for r in conn.execute(exact_sql, [q.strip(), q.strip()] + fparams)]
    sql = (f"SELECT f.path, f.name, f.entity, f.kind, f.year_month, f.purpose, f.certainty, f.size, {ext}, "
           "snippet(files_fts, 3, '[', ']', '…', 12) AS snippet, rank "
           "FROM files_fts JOIN files f ON f.path = files_fts.path WHERE files_fts MATCH ?") + frag \
        + " ORDER BY rank LIMIT ?"
    try:
        rows = conn.execute(sql, [match] + fparams + [limit]).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute(sql, [q] + fparams + [limit]).fetchall()
    seen = {r["path"] for r in exact}
    merged = exact + [dict(r) for r in rows if r["path"] not in seen]
    if vec_paths:
        return fuse(conn, merged, vec_paths, frag, fparams, limit, ext)
    return merged[:limit]


def embed_paths(db: Path, q: str, k: int) -> list[str] | None:
    """Hits from tools/index/embed/embed.py search(index_db_path, query, k), or None when that module is absent."""
    if not EMBED_FILE.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("_index_embed_query", EMBED_FILE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, "search", None)
        if not callable(fn):
            return None
        hits = fn(str(db), q, k) or []
    except Exception as e:  # noqa: BLE001 - full-text search still works without the embedder
        if os.environ.get("INDEX_DEBUG"):
            print(f"embedding search skipped: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    out = []
    for h in hits:
        if isinstance(h, dict):
            p = h.get("path")
        elif isinstance(h, (list, tuple)):
            p = h[0] if h else None
        else:
            p = h
        if p:
            out.append(str(p))
    return out


def parse_record_filters(tokens: list[str]) -> tuple[list[tuple[str, str]], str]:
    pairs: list[tuple[str, str]] = []
    words: list[str] = []
    for t in tokens:
        if "=" in t:
            k, v = t.split("=", 1)
            k = k.strip().lower()
            if k not in RECORD_KEYS:
                sys.exit(f"unknown record filter '{k}'. Allowed: {', '.join(sorted(RECORD_KEYS))}")
            pairs.append((k, v.strip()))
        else:
            words.append(t)
    return pairs, " ".join(words)


def cmd_records(conn: sqlite3.Connection, tokens: list[str], limit: int) -> list[dict]:
    if not table_exists(conn, "records"):
        sys.exit("no records table yet: run tools/index/migrate.py")
    pairs, words = parse_record_filters(tokens)
    clauses: list[str] = []
    params: list = []
    for key, raw in pairs:
        if key in RECORD_EQ:
            vals = [x.strip() for x in raw.split(",") if x.strip()]
            if not vals:
                sys.exit(f"{key} needs a value")
            clauses.append(f"{RECORD_EQ[key]} IN ({','.join('?' * len(vals))})")
            params += vals
        elif key in RECORD_LIKE:
            clauses.append(f"{RECORD_LIKE[key]} LIKE ?")
            params.append(f"%{raw}%")
        elif key in RECORD_DATE:
            if not re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", raw):
                sys.exit(f"{key} needs YYYY-MM or YYYY-MM-DD, got '{raw}'")
            col, op = RECORD_DATE[key]
            clauses.append(f"{col} {op} ?")
            params.append(raw)
        elif key in RECORD_NUM:
            try:
                num = float(raw)
            except ValueError:
                sys.exit(f"{key} needs a number, got '{raw}'")
            op = RECORD_NUM[key][0]
            clauses.append(f"amount {op} ?")
            params.append(num)
    if words:
        clauses.append("(title LIKE ? OR counterparty LIKE ? OR ref LIKE ? OR extra LIKE ?)")
        params += [f"%{words}%"] * 4
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT {RECORD_COLS} FROM records{where} ORDER BY (due_date IS NULL), due_date, date, id LIMIT ?"
    return [dict(r) for r in conn.execute(sql, params + [limit])]


def format_record(r: dict) -> str:
    if r.get("amount_text"):
        amt = r["amount_text"]
    elif r.get("amount") is not None:
        amt = f"{r['amount']} {r.get('currency') or ''}".strip()
    else:
        amt = "-"
    return "\n".join([
        f"{r['kind']} {r.get('ref') or '(no ref)'}  company={r.get('company') or '-'} "
        f"status={r.get('status') or '-'} due={r.get('due_date') or '-'} date={r.get('date') or '-'}",
        f"    {r.get('title') or ''}  counterparty={r.get('counterparty') or '-'}  amount={amt}",
        f"    source={r['source_path']}:{r.get('source_line') or '-'}",
    ])


def cmd_info(conn: sqlite3.Connection, path: str) -> dict | None:
    row = conn.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()
    if not row:
        row = conn.execute("SELECT * FROM files WHERE path LIKE ?", (f"%/{path}",)).fetchone()
    if not row:
        return None
    rec = dict(row)
    rec["edges_out"] = [dict(r) for r in conn.execute("SELECT dst, rel FROM edges WHERE src = ? LIMIT 50", (rec["path"],))]
    rec["edges_in"] = [dict(r) for r in conn.execute("SELECT src, rel FROM edges WHERE dst = ? LIMIT 50", (rec["path"],))]
    return rec


def cmd_stats(conn: sqlite3.Connection) -> dict:
    meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}

    def counts(col: str) -> dict:
        return {(r[0] if r[0] is not None else "(not set)"): r[1] for r in conn.execute(
            f"SELECT {col}, COUNT(*) AS n FROM files GROUP BY {col} ORDER BY n DESC")}

    cols = table_columns(conn, "files")
    data = {"meta": meta, "by_entity": counts("entity"), "by_kind": counts("kind")}
    data["by_area"] = counts("area") if "area" in cols else None
    data["by_tier"] = counts("tier") if "tier" in cols else None
    data["records_total"] = (conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
                             if table_exists(conn, "records") else None)
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description="Query vault_index.db")
    ap.add_argument("--db", default=None)
    ap.add_argument("--root", default=os.environ.get("BRAIN_ROOT") or str(HERE.parents[1]))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--entity", default=None)
    ap.add_argument("--area", default=None, choices=AREAS)
    ap.add_argument("--tier", default=None, choices=TIERS)
    ap.add_argument("--all", action="store_true", help="include tier archive")
    ap.add_argument("--no-embed", action="store_true", help="full-text only, even if an embedder exists")
    ap.add_argument("--records", action="store_true", help="search the records table (kind=... status=... ...)")
    ap.add_argument("--info", metavar="PATH", default=None)
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("query", nargs="*")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    db = Path(args.db) if args.db else root / ".index" / "vault_index.db"
    conn = connect(db)

    if args.stats:
        data = cmd_stats(conn)
        stamp(root, "stats", "")
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"built_at={data['meta'].get('built_at')} files={data['meta'].get('file_count')} "
                  f"edges={data['meta'].get('edge_count')} purpose={data['meta'].get('purpose_count')} "
                  f"schema={data['meta'].get('schema_version', '1')} records={data['records_total']}")
            for k, n in data["by_entity"].items():
                print(f"  {k}: {n}")
            for label in ("by_area", "by_tier"):
                if data[label]:
                    print(f"  {label}: " + ", ".join(f"{k}={n}" for k, n in data[label].items()))
        return

    if args.info:
        rec = cmd_info(conn, args.info)
        if rec is None:
            sys.exit(f"not in index: {args.info}")
        stamp(root, "info", args.info)
        if args.json:
            print(json.dumps(rec, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"{rec['path']}\n  entity={rec['entity']} kind={rec['kind']} ym={rec['year_month']} "
                  f"area={rec.get('area')} tier={rec.get('tier')} doc_date={rec.get('doc_date')}")
            print(f"  purpose={rec['purpose']!r} certainty={rec['certainty']}")
            print(f"  digest={rec['digest_path']} sha256={rec['sha256']}")
        return

    if args.records:
        tokens = args.query
        if not tokens:
            sys.exit("usage: query.py --records kind=invoice status=open company=DE due_before=2030-12-01 [WORDS]")
        rows = cmd_records(conn, tokens, args.limit)
        stamp(root, "records", " ".join(tokens))
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
            return
        if not rows:
            print("no records")
            return
        for r in rows:
            print(format_record(r))
        return

    q = " ".join(args.query).strip()
    if not q:
        sys.exit("usage: query.py [--json] [--entity DE] [--area A] [--tier T] [--all] SEARCH\n"
                 "       query.py --records kind=... status=... company=... due_before=...\n"
                 "       query.py --info PATH\n       query.py --stats")
    vec = None if args.no_embed else embed_paths(db, q, max(args.limit * 3, 30))
    rows = cmd_search(conn, q, args.limit, args.entity, args.area, args.tier, args.all, vec or None)
    stamp(root, "search", q)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        return
    if not rows:
        print("no hits")
        return
    for r in rows:
        print(f"{r['path']}")
        if r.get("area") or r.get("tier"):
            print(f"  area={r.get('area') or '-'} tier={r.get('tier') or '-'}")
        if r.get("purpose"):
            print(f"  {r['purpose']}")
        if r.get("snippet"):
            print(f"  {r['snippet']}")


if __name__ == "__main__":
    main()
