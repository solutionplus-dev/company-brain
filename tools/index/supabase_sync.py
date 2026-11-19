#!/usr/bin/env python3
"""Fill the Supabase brain store from the local index, scope by scope. Standard library only.

  python3 tools/index/supabase_sync.py [--plan]                 what would go, per scope (no network)
  python3 tools/index/supabase_sync.py --apply [--scopes a,b]   upsert; no --scopes = every allowed scope
  python3 tools/index/supabase_sync.py --verify [--scopes a,b]  remote row counts against the plan
  python3 tools/index/supabase_sync.py --backup                 every brain table into .index/supabase_backup.db
  python3 tools/index/supabase_sync.py search "question" [--scopes a,b] [-k 20]
  Another brain:  --walk DIR --source NAME --scope S [--module M] [--prefix P]
  Smoke test:     --apply --scopes design --limit 5             (no deletions while --limit is set)

Rules: tools/index/supabase/scopes.json. Secrets: read from .env by name (supabase_url,
supabase_project_ref, supabase_secret_key or --key-var supabase_legacy_service_role_key); never
printed. Output is counts only. Exit codes: 0 ok, 1 usage/config, 2 refused, 3 verify mismatch,
4 key refused (401/403), 5 remote error, 6 local source missing.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("BRAIN_ROOT") or HERE.parents[1]).resolve()
sys.path.insert(0, str(HERE / "supabase"))
import brain_redact  # noqa: E402
import brain_rest as R  # noqa: E402
import brain_sync_lib as L  # noqa: E402

TOOL_VERSION = "brain-sync/1"
EXIT_OK, EXIT_USAGE, EXIT_REFUSED, EXIT_MISMATCH, EXIT_AUTH, EXIT_REMOTE, EXIT_LOCAL = 0, 1, 2, 3, 4, 5, 6
KEY_VARS = ("supabase_secret_key", "supabase_legacy_service_role_key")
BACKUP_TABLES = [
    ("brain_documents", "id", ["id", "scope", "module", "source", "path", "sha256", "text_key", "redaction", "title",
                               "area", "tier", "company", "doc_date", "has_digest", "size", "n_chunks",
                               "updated_at", "synced_at"]),
    ("brain_chunks", "id", ["id", "document_id", "scope", "ord", "text"]),
    ("brain_embeddings", "chunk_id", ["chunk_id", "scope", "bin", "full", "model"]),
    ("brain_records", "id", ["id", "scope", "source", "kind", "company", "ref", "title", "date", "due_date", "amount",
                             "amount_text", "currency", "counterparty", "status", "certainty", "client", "account",
                             "debit", "credit", "source_path", "source_line", "extra", "synced_at"]),
    ("brain_edges", "id", ["id", "scope", "source", "src", "dst", "rel"]),
    ("brain_sync_runs", "id", ["id", "scope", "source", "module", "mode", "tool_version", "started_at", "finished_at",
                               "status", "documents", "chunks", "embeddings", "records", "edges", "deleted",
                               "blocked", "redacted_chunks", "note"]),
    ("brain_members", "user_id", ["user_id", "scopes", "note", "created_at", "updated_at"]),
    ("brain_health", "scope", ["scope", "documents", "chunks", "embeddings", "records", "edges", "newest_synced_at",
                               "documents_without_chunks", "chunks_without_embeddings", "refreshed_at"]),
]


def out(msg=""):
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def now():
    return datetime.now(timezone.utc).isoformat()


# ----------------------------------------------------------------- setup

def make_builder(a, cfg):
    if a.walk:
        if not a.source or not L.SOURCE_RE.match(a.source):
            raise SystemExit(usage("--walk needs --source NAME (lowercase letters, digits, . _ -)"))
        if a.scope and not L.SCOPE_RE.match(a.scope):
            raise SystemExit(usage("--scope is not a valid scope name"))
        prefix = a.prefix if a.prefix is not None else f"Repos/{a.source}/"
        reason = walk_refusal(a.walk, a.scope)
        if reason and getattr(a, "apply", False):
            # a walked brain decides for itself whether it may leave this computer
            raise SystemExit(usage(f"--apply refused for this brain: {reason}"))
        if reason:
            sys.stderr.write(f"supabase_sync: note: an upload of this brain would be refused: {reason}\n")
        src = L.WalkSource(a.walk, prefix, a.source)
        return L.Builder(cfg, src, a.scope, a.module or a.source.replace(".", "-")[:63])
    src = L.IndexSource(a.index_db, a.vectors_db, ROOT, a.source or "vault")
    return L.Builder(cfg, src)


def walk_refusal(directory, scope=None):
    """Why a walked brain may not be uploaded, or None. A brain that carries `brain/DATA_HANDLING.md`
    (the client-brain template) is uploaded only if that file has a line `sync: yes` and does not
    declare the data class `special` (health data) or `nda`. A folder without that file is a module
    repository and is governed by scopes.json and its own hook."""
    import os, re
    f = os.path.join(directory, "brain", "DATA_HANDLING.md")
    if not os.path.isfile(f):
        if scope and scope.startswith("client:"):
            # a client scope is only ever filled from a brain that says so itself
            return "a client scope needs brain/DATA_HANDLING.md with a line 'sync: yes' in the walked folder"
        return None
    try:
        text = open(f, encoding="utf-8", errors="replace").read()
    except OSError:
        return "brain/DATA_HANDLING.md could not be read"
    m = re.search(r"data class\s*\|?\s*[:|]?\s*`?(special|nda)`?", text, re.I)
    if m:
        return f"data class {m.group(1).lower()} never leaves this computer"
    if not re.search(r"^\s*sync:\s*yes\s*$", text, re.I | re.M):
        return "brain/DATA_HANDLING.md has no line 'sync: yes'"
    return None


def usage(msg):
    sys.stderr.write(f"supabase_sync: {msg}\n")
    return EXIT_USAGE


def rest_client(a):
    env = R.read_env(a.env_file, {"supabase_url", "supabase_project_ref", a.key_var})
    if "supabase_url" not in env:
        raise R.RefusedError("the .env variable 'supabase_url' is missing")
    if a.key_var not in env:
        raise R.RefusedError(f"the .env variable '{a.key_var}' is missing")
    ref = env.get("supabase_project_ref")
    base = R.check_url(env["supabase_url"].reveal(), ref.reveal() if ref else None, a.allow_loopback)
    return R.Rest(base, env[a.key_var], debug=a.debug)


def pick_scopes(a, cfg, b, strict=True):
    known = set(b.docs)
    if a.walk and a.scope:
        known.add(a.scope)
    if a.scopes:
        req = [s.strip() for s in a.scopes.split(",") if s.strip()]
    else:
        req = sorted(known)
        strict = False
    chosen, refused = [], []
    for s in req:
        ok, why = cfg.scope_allowed(s)
        (chosen if ok else refused).append((s, why))
    if refused and strict:
        for s, why in refused:
            sys.stderr.write(f"refused: scope {s}: {why}\n")
        raise R.RefusedError("nothing was sent")
    for s, why in refused:
        out(f"skipped scope {s}: {why}")
    return [s for s, _ in chosen]


# ----------------------------------------------------------------- plan

def plan_counts(b, scopes=None, limit=None):
    """Per scope: docs, docs_text, chunks, vectors, redacted, dropped (loads every chunk, keeps none)."""
    res = {}
    for s, docs in sorted(b.docs.items()):
        if scopes is not None and s not in scopes:
            continue
        docs = docs[:limit] if limit else docs
        c = {"docs": len(docs), "docs_text": 0, "chunks": 0, "vectors": 0, "redacted": 0, "dropped": 0}
        for d in docs:
            ch, em, st = b.chunk_rows(d)
            c["docs_text"] += 1 if ch else 0
            c["chunks"] += len(ch)
            c["vectors"] += len(em)
            c["redacted"] += st["redacted"]
            c["dropped"] += st["dropped"]
        res[s] = c
    return res


def cmd_plan(a, cfg, b):
    recs, rst = b.record_rows()
    edges = b.edge_rows()
    pc = plan_counts(b)
    src = b.src
    vec = "present" if src.has_vectors else "absent (text from the catalogue, no vectors)"
    out(f"Brain sync plan (no network). source={src.source}  vectors.db: {vec}")
    out(f"redaction: {brain_redact.describe()}")
    out(f"owner_confirmed_private_scopes: {cfg.flag}   client_scopes_allowed: {sorted(cfg.client_allowed) or 'none'}")
    hdr = f"{'scope':<28}{'status':<9}{'docs':>7}{'w/text':>8}{'chunks':>8}{'vectors':>9}{'records':>9}{'edges':>7}{'never':>7}{'redact':>8}{'drop':>6}"
    out(hdr)
    out("-" * len(hdr))
    scopes = sorted(set(pc) | set(recs) | {k for k in b.blocked if k != "(none)"})
    tot = dict.fromkeys(["docs", "docs_text", "chunks", "vectors", "records", "edges", "never", "redacted", "dropped"], 0)
    for s in scopes:
        c = pc.get(s, {"docs": 0, "docs_text": 0, "chunks": 0, "vectors": 0, "redacted": 0, "dropped": 0})
        ok, why = cfg.scope_allowed(s)
        row = dict(c, records=len(recs.get(s, [])), edges=len(edges.get(s, [])), never=b.blocked.get(s, 0))
        for k in tot:
            tot[k] += row[k]
        out(f"{s:<28}{'ready' if ok else 'REFUSED':<9}{row['docs']:>7}{row['docs_text']:>8}{row['chunks']:>8}"
            f"{row['vectors']:>9}{row['records']:>9}{row['edges']:>7}{row['never']:>7}{row['redacted']:>8}{row['dropped']:>6}")
    out("-" * len(hdr))
    out(f"{'total':<37}{tot['docs']:>7}{tot['docs_text']:>8}{tot['chunks']:>8}{tot['vectors']:>9}"
        f"{tot['records']:>9}{tot['edges']:>7}{tot['never']:>7}{tot['redacted']:>8}{tot['dropped']:>6}")
    out(f"never-listed with no scope of their own: {b.blocked.get('(none)', 0)}")
    out(f"stay local by rule: {b.local.get('local-rule', 0)}   unmapped (stay local): {b.local.get('unmapped', 0)}")
    out(f"records: blocked by never list {rst['blocked']}, stay local {rst['local']}, dropped for never terms "
        f"{rst['dropped']}, invalid ledger lines {rst['invalid']}, duplicates {rst['duplicate']}, "
        f"rows with redactions {rst['redacted']}")
    refused = [s for s in scopes if not cfg.scope_allowed(s)[0]]
    if refused:
        out("refused scopes: " + ", ".join(f"{s} ({cfg.scope_allowed(s)[1]})" for s in refused))
    out("columns: never = files blocked by the never list that this scope would otherwise get; redact = chunks "
        "the redactor changed; drop = chunks dropped for never_text_terms")
    return EXIT_OK


# ----------------------------------------------------------------- apply

def sync_scope(rest, a, b, scope, recs, edges):
    src = b.src.source
    docs = b.docs.get(scope, [])
    limit = a.limit
    if limit:
        docs = docs[:limit]
        keep = {d["row"]["path"] for d in docs}
        recs = recs[:limit]
        edges = [e for e in edges if e["src"] in keep]
    _, _, run = rest.request("POST", "brain_sync_runs", [("select", "id")],
                             [{"scope": scope, "source": src, "mode": "apply" + (f"-limit{limit}" if limit else ""),
                               "tool_version": TOOL_VERSION, "status": "running"}],
                             {"Prefer": "return=representation"})
    run_id = run[0]["id"]
    c = dict.fromkeys(["documents", "chunks", "embeddings", "records", "edges", "deleted", "redacted_chunks"], 0)
    try:
        flt = [("scope", "eq." + scope), ("source", "eq." + src)]
        remote = {r["id"]: r for r in rest.get_all("brain_documents", "id,text_key,n_chunks", flt, "id.asc")}
        changed, rows = [], []
        for d in docs:
            row, fp = dict(d["row"]), b.fingerprint(d)
            r = remote.get(row["id"])
            if r and r.get("text_key") == fp and (fp is not None or not r.get("n_chunks")):
                row["text_key"], row["n_chunks"] = fp, r.get("n_chunks") or 0
            else:
                changed.append((d, fp, r is not None))
            rows.append(row)
        rest.upsert("brain_documents", rows, "id", a.batch_docs)
        c["documents"] = len(rows)
        for i in range(0, len(changed), 25):
            part = changed[i:i + 25]
            old = [d["row"]["id"] for d, _, existed in part if existed]
            if old:
                rest.delete_in("brain_chunks", scope, "document_id", old)
            ch_all, em_all, done = [], [], []
            for d, fp, _ in part:
                ch, em, st = b.chunk_rows(d)
                ch_all += ch
                em_all += em
                c["redacted_chunks"] += st["redacted"]
                done.append(dict(d["row"], text_key=fp, n_chunks=len(ch)))
            rest.upsert("brain_chunks", ch_all, "id", a.batch_chunks)
            for j in range(0, len(em_all), a.batch_vectors):
                rest.upsert("brain_embeddings", [b.embedding_payload(e) for e in em_all[j:j + a.batch_vectors]],
                            "chunk_id", a.batch_vectors)
            rest.upsert("brain_documents", done, "id", a.batch_docs)
            c["chunks"] += len(ch_all)
            c["embeddings"] += len(em_all)
        local_ids = {d["row"]["id"] for d in docs}
        if not limit:
            c["deleted"] += rest.delete_in("brain_documents", scope, "id", sorted(set(remote) - local_ids),
                                           extra=[("source", "eq." + src)])
        for table, rows_, key in (("brain_records", recs, "records"), ("brain_edges", edges, "edges")):
            have = {r["id"] for r in rest.get_all(table, "id", flt, "id.asc")}
            rest.upsert(table, rows_, "id", a.batch_records)
            c[key] = len(rows_)
            if not limit:
                c["deleted"] += rest.delete_in(table, scope, "id", sorted(have - {r["id"] for r in rows_}),
                                               extra=[("source", "eq." + src)])
        status, note = "ok", f"changed documents {len(changed)}"
    except BaseException as exc:
        status, note = "failed", exc.__class__.__name__
        raise
    finally:
        try:
            rest.request("PATCH", "brain_sync_runs", [("id", f"eq.{run_id}")],
                         {"finished_at": now(), "status": status, "blocked": b.blocked.get(scope, 0),
                          "note": note, **c}, {"Prefer": "return=minimal"})
        except R.RestError:
            pass
    out(f"{scope:<24} documents {c['documents']}, chunks {c['chunks']}, vectors {c['embeddings']}, "
        f"records {c['records']}, edges {c['edges']}, deleted {c['deleted']}, redacted chunks {c['redacted_chunks']}")
    return c


def cmd_apply(a, cfg, b):
    scopes = pick_scopes(a, cfg, b)
    if not scopes:
        out("no scope to sync")
        return EXIT_OK
    rest = rest_client(a)
    recs, _ = b.record_rows()
    edges = b.edge_rows()
    if a.limit:
        out(f"--limit {a.limit}: smoke test, nothing is deleted")
    for s in scopes:
        sync_scope(rest, a, b, s, recs.get(s, []), edges.get(s, []))
    return EXIT_OK


# ----------------------------------------------------------------- verify / backup / search

def cmd_verify(a, cfg, b):
    scopes = pick_scopes(a, cfg, b, strict=False)
    rest = rest_client(a)
    recs, _ = b.record_rows()
    edges = b.edge_rows()
    pc = plan_counts(b, set(scopes))
    bad = 0
    out(f"{'scope':<24}{'table':<18}{'local':>8}{'remote':>8}")
    for s in scopes:
        flt = [("scope", "eq." + s)]
        srcf = flt + [("source", "eq." + b.src.source)]
        p = pc.get(s, {"docs": 0, "chunks": 0, "vectors": 0})
        checks = [("brain_documents", p["docs"], srcf), ("brain_chunks", p["chunks"], None),
                  ("brain_embeddings", p["vectors"], None), ("brain_records", len(recs.get(s, [])), srcf),
                  ("brain_edges", len(edges.get(s, [])), srcf)]
        for table, want, f in checks:
            if f is None:  # chunks and embeddings carry no source column: counted per scope
                got = rest.count(table, flt)
            else:
                got = rest.count(table, f)
            flag = "" if got == want else "  MISMATCH"
            bad += 1 if flag else 0
            out(f"{s:<24}{table:<18}{want:>8}{got:>8}{flag}")
    out("verify: OK" if not bad else f"verify: {bad} mismatches")
    return EXIT_OK if not bad else EXIT_MISMATCH


def _to_sqlite(table, col, v):
    if v is None:
        return None
    if table == "brain_embeddings" and col == "bin":
        return bytes(int(v[i:i + 8], 2) for i in range(0, len(v), 8))
    if table == "brain_embeddings" and col == "full":
        vals = json.loads(v) if isinstance(v, str) else v
        return struct.pack(f"<{len(vals)}e", *vals)
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return int(v)
    return v


def cmd_backup(a, cfg, b):
    rest = rest_client(a)
    dest = Path(a.backup_db)
    tmp = dest.with_name(dest.name + ".partial")
    if tmp.exists():
        tmp.unlink()  # our own half-written file from an interrupted run
    con = sqlite3.connect(str(tmp))
    con.execute("create table backup_meta (key text primary key, value text)")
    counts = {}
    for table, pk, cols in BACKUP_TABLES:
        try:
            rows = rest.get_all(table, ",".join(cols), [], f"{pk}.asc")
        except R.RestError as exc:
            if exc.status == 404 or exc.code in ("42P01", "PGRST205"):
                counts[table] = "absent"
                continue
            raise
        types = {c: ("BLOB" if table == "brain_embeddings" and c in ("bin", "full") else "") for c in cols}
        con.execute(f"create table {table} (" + ", ".join(f'"{c}" {types[c]}'.strip() for c in cols) + ")")
        con.executemany(f"insert into {table} values ({','.join('?' * len(cols))})",
                        [[_to_sqlite(table, c, r.get(c)) for c in cols] for r in rows])
        counts[table] = len(rows)
    con.execute("insert into backup_meta values ('taken_at', ?), ('tool', ?)", (now(), TOOL_VERSION))
    con.commit()
    con.close()
    os.replace(tmp, dest)
    for t, n in counts.items():
        out(f"{t:<20} {n}")
    out(f"backup written: {dest}")
    return EXIT_OK


def embed_query(question):
    venv = ROOT / "tools" / "index" / ".venv" / "bin" / "python"
    helper = HERE / "supabase" / "embed_query.py"
    if not venv.exists():
        return None
    try:
        p = subprocess.run([str(venv), str(helper)], input=question, capture_output=True, text=True, timeout=600)
        line = [x for x in p.stdout.splitlines() if x.startswith("EMBED_QUERY_JSON:")]
        return json.loads(line[-1][len("EMBED_QUERY_JSON:"):]) if line else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def cmd_search(a, cfg):
    q = embed_query(a.query) if not a.text_only else None
    if q is None:
        out("(no local embedder: text search only)")
    rest = rest_client(a)
    want = [s.strip() for s in a.scopes.split(",")] if a.scopes else None
    body = {"query_bin": q["bin"] if q else None,
            "query_full": L.halfvec_text(q["full"]) if q else None,
            "query_text": a.query, "k": a.k, "want_scopes": want}
    _, _, hits = rest.request("POST", "rpc/brain_search", [], body)
    for i, h in enumerate(hits or [], 1):
        out(f"{i:>3}  {h.get('score') or 0:.5f}  {h.get('scope'):<16} {h.get('path')}")
    if not hits:
        out("no hits")
    return EXIT_OK


# ----------------------------------------------------------------- main

def parse(argv):
    p = argparse.ArgumentParser(prog="supabase_sync.py", description=__doc__.split("\n")[0])
    m = p.add_mutually_exclusive_group()
    for flag in ("--plan", "--apply", "--verify", "--backup"):
        m.add_argument(flag, action="store_true")
    p.add_argument("command", nargs="?", choices=["search"])
    p.add_argument("query", nargs="?")
    p.add_argument("--scopes")
    p.add_argument("--limit", type=int)
    p.add_argument("-k", type=int, default=20)
    p.add_argument("--text-only", action="store_true")
    p.add_argument("--config", default=str(HERE / "supabase" / "scopes.json"))
    p.add_argument("--index-db", default=str(ROOT / ".index" / "vault_index.db"))
    p.add_argument("--vectors-db", default=str(ROOT / ".index" / "vectors.db"))
    p.add_argument("--backup-db", default=str(ROOT / ".index" / "supabase_backup.db"))
    p.add_argument("--env-file", default=str(ROOT / ".env"))
    p.add_argument("--key-var", default=KEY_VARS[0], choices=KEY_VARS)
    p.add_argument("--walk")
    p.add_argument("--source")
    p.add_argument("--scope")
    p.add_argument("--module")
    p.add_argument("--prefix")
    p.add_argument("--batch-docs", type=int, default=500)
    p.add_argument("--batch-chunks", type=int, default=200)
    p.add_argument("--batch-vectors", type=int, default=100)
    p.add_argument("--batch-records", type=int, default=500)
    p.add_argument("--debug", action="store_true", help="trace requests (keys redacted)")
    p.add_argument("--allow-loopback", action="store_true", help=argparse.SUPPRESS)
    a = p.parse_args(argv)
    if a.command == "search" and not a.query:
        p.error("search needs a question")
    if a.limit is not None and a.limit < 1:
        p.error("--limit must be 1 or more")
    return a


def main(argv=None):
    a = parse(sys.argv[1:] if argv is None else argv)
    try:
        cfg = L.ScopeConfig.load(a.config)
        if a.command == "search":
            return cmd_search(a, cfg)
        if a.backup:
            return cmd_backup(a, cfg, None)
        b = make_builder(a, cfg)
        if a.apply:
            return cmd_apply(a, cfg, b)
        if a.verify:
            return cmd_verify(a, cfg, b)
        return cmd_plan(a, cfg, b)
    except L.ConfigError as e:
        sys.stderr.write(f"config error: {e}\n")
        return EXIT_USAGE
    except L.LocalError as e:
        sys.stderr.write(f"local source: {e}\n")
        return EXIT_LOCAL
    except R.RefusedError as e:
        sys.stderr.write(f"refused: {e}\n")
        return EXIT_REFUSED
    except R.AuthError as e:
        sys.stderr.write(f"{e}\n")
        return EXIT_AUTH
    except R.RestError as e:
        sys.stderr.write(f"remote error: {e}\n")
        return EXIT_REMOTE


if __name__ == "__main__":
    sys.exit(main())
