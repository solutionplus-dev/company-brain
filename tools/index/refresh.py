#!/usr/bin/env python3
"""Refresh the vault catalog (.index/vault_index.db). Stdlib only.

  python3 tools/index/refresh.py            incremental (default): re-extract files whose size or mtime changed, add new
                                            files, drop DB rows of vanished files. A file that vanished from one path and
                                            appeared at another with the same sha256 is a MOVE: its row keeps its rowid
                                            and takes the new path (records and edges follow). One SQLite transaction.
  python3 tools/index/refresh.py --full     full rebuild in one process, then atomic replace. Tables other than files,
                                            edges and meta (records, runs, and any table another lane adds) are carried over.
  python3 tools/index/refresh.py --dry-run  report what an incremental run would do; writes nothing.

After the file pass, two optional steps run, each in its own try/except; a failure is written to runs.errors and never
stops the refresh:
  tools/index/importers/run_all.py   run(db_path) -> count      (records and their edges)
  tools/index/embed/embed.py         embed_pending(db_path) -> count
Every real run writes one `runs` row and .index/index_stats.json. Never touches a vault file; DB rows are removed for
vanished files, files are never removed.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ in the vault
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import brainconfig  # noqa: E402
import extract_chunk as ex  # noqa: E402
import migrate as mg  # noqa: E402
from build_index import FILE_COLS, SCHEMA  # noqa: E402

# Linked repositories under Repos/ are not catalogued here: each has its own brain and its own index.
# `_archive` is deliberately NOT skipped: archived folders are catalogued with tier=archive, which hides them
# from default searches (query.py --all shows them).
EXTRA_SKIP_DIRS = {"Repos"}
ex.SKIP_DIRS.update(EXTRA_SKIP_DIRS)

DEFAULT_PREFIXES = brainconfig.prefixes()
# Top-level folders that are deliberately not indexed (stale copies, scratch, other tools' output).
DELIBERATE_SKIP_PREFIXES = ("_backup_", "_tmp_")
# Outputs of this script: never catalogued (the stats file changes on every run).
SELF_OUTPUTS: set = set()
IMPORTER_FILE = HERE / "importers" / "run_all.py"
EMBED_FILE = HERE / "embed" / "embed.py"
# Tables that a full rebuild rebuilds itself. Every other table of the old database is carried over.
CARRY_SKIP = {"files", "edges", "meta"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def git_head(root: Path) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def prefixes_from_db(conn: sqlite3.Connection) -> list[str]:
    out = list(DEFAULT_PREFIXES)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='prefixes'").fetchone()
        for item in json.loads(row[0]) if row else []:
            if isinstance(item, list):
                for p in item:
                    if p not in out:
                        out.append(p)
    except (sqlite3.Error, json.JSONDecodeError, TypeError):
        pass
    return out


def scan_disk(root: Path, prefixes: list[str]) -> dict[str, tuple[int, int]]:
    """rel path -> (size, mtime), with exactly the walk rules of extract_chunk.walk_prefix + root files."""
    found: dict[str, tuple[int, int]] = {}
    for prefix in prefixes:
        base = root / prefix
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if not ex.should_skip_dir(d))
            for fn in filenames:
                if fn.startswith(ex.SKIP_FILE_PREFIX):
                    continue
                p = Path(dirpath) / fn
                if not p.is_file():
                    continue
                rel = ex.rel_to(root, p)
                if rel in SELF_OUTPUTS or brainconfig.ignored(rel, root):
                    continue
                try:
                    st = p.stat()
                except OSError:
                    continue
                found[rel] = (int(st.st_size), int(st.st_mtime))
    for p in sorted(root.iterdir()):  # files on the vault root
        if not p.is_file() or p.name.startswith("."):
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        found.setdefault(p.name, (int(st.st_size), int(st.st_mtime)))
    return found


def unindexed_top_level(root: Path, prefixes: list[str]) -> list[str]:
    out = []
    for p in sorted(root.iterdir()):
        if not p.is_dir() or p.name.startswith(".") or p.name in ex.SKIP_DIRS or p.name in ("_archive", *EXTRA_SKIP_DIRS):
            continue
        if p.name in prefixes or p.name.startswith(DELIBERATE_SKIP_PREFIXES):
            continue
        out.append(p.name)
    return out


def record_for(root: Path, rel: str, today: date | None = None) -> tuple[dict, list[dict]] | None:
    """Full catalog record (with derived fields) for one file, or None if it cannot be read."""
    p = root / rel
    try:
        st = p.stat()
    except OSError:
        return None
    if "/" not in rel:  # root file
        rec, edges = ex.root_file_record(root, p, st), []
    else:
        rec, edges = ex.file_record(root, p, st)
    rec.update(mg.derive_fields(rec, today))
    return rec, edges


def pair_moves(gone_sha: dict[str, str | None], new_sha: dict[str, str | None]) -> list[tuple[str, str]]:
    """Pair vanished paths with new paths of the same sha256: a file that was moved. Files without a hash never pair."""
    by_sha: dict[str, list[str]] = defaultdict(list)
    for g in sorted(gone_sha):
        if gone_sha[g]:
            by_sha[gone_sha[g]].append(g)
    used: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for n in sorted(new_sha):
        s = new_sha[n]
        if not s:
            continue
        cands = [g for g in by_sha.get(s, []) if g not in used]
        if not cands:
            continue
        same_name = [g for g in cands if Path(g).name == Path(n).name]
        g = (same_name or cands)[0]
        used.add(g)
        pairs.append((g, n))
    return pairs


# ----------------------------------------------------------------------------- db ops
def insert_edges(conn: sqlite3.Connection, edges: list[dict], dedupe: bool = False) -> None:
    for e in edges:
        src, dst, rel = e.get("src"), e.get("dst"), e.get("rel")
        if not (src and dst and rel):
            continue
        if dedupe:
            conn.execute("INSERT INTO edges (src, dst, rel) SELECT ?,?,? WHERE NOT EXISTS "
                         "(SELECT 1 FROM edges WHERE src=? AND dst=? AND rel=?)", (src, dst, rel) * 2)
        else:
            conn.execute("INSERT INTO edges (src, dst, rel) VALUES (?,?,?)", (src, dst, rel))


def insert_record(conn: sqlite3.Connection, rec: dict, edges: list[dict], chunk_id: str,
                  today: date | None = None) -> None:
    rec.update(mg.derive_fields(rec, today))
    row = {k: rec.get(k) for k in FILE_COLS}
    row["chunk_id"] = chunk_id
    cur = conn.execute(f"INSERT INTO files ({','.join(FILE_COLS)}) VALUES ({','.join('?' * len(FILE_COLS))})",
                       [row[k] for k in FILE_COLS])
    conn.execute("INSERT INTO files_fts (rowid, path, name, purpose, digest_text, entity) VALUES (?,?,?,?,?,?)",
                 [cur.lastrowid, rec["path"], rec.get("name") or "", rec.get("purpose") or "",
                  rec.get("digest_text") or "", rec.get("entity") or ""])
    insert_edges(conn, edges)


def delete_path(conn: sqlite3.Connection, path: str) -> None:
    row = conn.execute("SELECT rowid FROM files WHERE path=?", (path,)).fetchone()
    if row:
        conn.execute("DELETE FROM files_fts WHERE rowid=?", (row[0],))
        conn.execute("DELETE FROM files WHERE path=?", (path,))
    conn.execute("DELETE FROM edges WHERE src=? OR (dst=? AND rel='digest_of')", (path, path))


def move_path(conn: sqlite3.Connection, old: str, new: str, rec_edges: tuple[dict, list[dict]],
              today: date | None = None) -> None:
    """A moved file keeps its row (rowid) and takes the new path. Records and edges that name the old path follow it."""
    rec, edges = rec_edges
    rec.update(mg.derive_fields(rec, today))
    row = conn.execute("SELECT rowid FROM files WHERE path=?", (old,)).fetchone()
    if row is None:
        raise RuntimeError(f"move source not in index: {old}")
    rid = row[0]
    cols = [c for c in FILE_COLS if c != "chunk_id"]  # chunk_id keeps the value of the first build
    conn.execute(f"UPDATE files SET {', '.join(c + '=?' for c in cols)} WHERE rowid=?",
                 [rec.get(c) for c in cols] + [rid])
    conn.execute("UPDATE files_fts SET path=?, name=?, purpose=?, digest_text=?, entity=? WHERE rowid=?",
                 [new, rec.get("name") or "", rec.get("purpose") or "", rec.get("digest_text") or "",
                  rec.get("entity") or "", rid])
    conn.execute("UPDATE OR IGNORE records SET source_path=? WHERE source_path=?", (new, old))
    conn.execute("UPDATE edges SET src=? WHERE src=?", (new, old))
    conn.execute("UPDATE edges SET dst=? WHERE dst=?", (new, old))
    conn.execute("DELETE FROM edges WHERE src=? AND rel='in_folder'", (new,))  # folder edge is re-derived below
    conn.execute("DELETE FROM edges WHERE dst=? AND rel='digest_of'", (new,))
    insert_edges(conn, edges, dedupe=True)


def integrity_ok(conn: sqlite3.Connection) -> bool:
    """files and files_fts must correspond 1:1 by rowid (the incremental delete and move rely on it)."""
    n_f = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    n_t = conn.execute("SELECT COUNT(*) FROM files_fts").fetchone()[0]
    if n_f != n_t:
        return False
    for rid, path in conn.execute("SELECT rowid, path FROM files ORDER BY rowid LIMIT 40"):
        r = conn.execute("SELECT path FROM files_fts WHERE rowid=?", (rid,)).fetchone()
        if not r or r[0] != path:
            return False
    return True


def update_meta(conn: sqlite3.Connection, root: Path, mode: str, stats: dict) -> None:
    n_files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    n_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    n_purp = conn.execute("SELECT COUNT(*) FROM files WHERE purpose IS NOT NULL AND purpose<>''").fetchone()[0]
    items = {"file_count": str(n_files), "edge_count": str(n_edges), "purpose_count": str(n_purp),
             "git_head": git_head(root), "refreshed_at": utc_now(), "refresh_mode": mode,
             "refresh_stats": json.dumps(stats, ensure_ascii=False), "schema_version": mg.SCHEMA_VERSION}
    for k, v in items.items():
        conn.execute("INSERT INTO meta (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))


def carry_over(conn: sqlite3.Connection, old_db: Path) -> list[str]:
    """Copy every table of the old database that the fresh build does not own (records, runs, others).

    Tables missing from the new file are re-created from the old CREATE statement; rows are copied for the columns
    both versions have. Runs after a commit (ATTACH is not allowed inside a transaction)."""
    conn.execute("ATTACH DATABASE ? AS old", (str(old_db),))
    carried: list[str] = []
    try:
        new_tables = set(mg.table_names(conn))
        old_tables = conn.execute("SELECT name, sql FROM old.sqlite_master WHERE type='table'").fetchall()
        for name, sql in old_tables:
            if name in CARRY_SKIP or name.startswith("sqlite_") or name.startswith("files_fts") or not sql:
                continue
            if "virtual" in sql.lower():
                continue
            if name not in new_tables:
                conn.execute(sql)
            new_cols = mg.table_columns(conn, name)
            old_cols = [r[1] for r in conn.execute(f'PRAGMA old.table_info("{name}")')]
            common = [c for c in new_cols if c in old_cols]
            if not common:
                continue
            cols = ", ".join(f'"{c}"' for c in common)
            cur = conn.execute(f'INSERT OR IGNORE INTO main."{name}" ({cols}) SELECT {cols} FROM old."{name}"')
            carried.append(f"{name}:{cur.rowcount}")
        conn.commit()
    finally:
        conn.execute("DETACH DATABASE old")
    return carried


def counts_from_maps(old_map: dict, new_map: dict) -> dict:
    """Full-rebuild counts: maps are path -> (sha256, size, mtime)."""
    old_p, new_p = set(old_map), set(new_map)
    added = sorted(new_p - old_p)
    removed = sorted(old_p - new_p)
    pairs = pair_moves({p: old_map[p][0] for p in removed}, {p: new_map[p][0] for p in added})
    changed = [p for p in old_p & new_p if old_map[p][1:] != new_map[p][1:]]
    return {"files_added": len(added) - len(pairs), "files_changed": len(changed),
            "files_removed": len(removed) - len(pairs), "files_moved": len(pairs)}


def log_run(root: Path, payload: dict) -> None:
    try:
        d = root / ".index"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "refresh_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ----------------------------------------------------------------------------- modes
def plan(conn: sqlite3.Connection, root: Path, prefixes: list[str]) -> dict:
    disk = scan_disk(root, prefixes)
    db = {r[0]: (r[1], r[2], r[3]) for r in conn.execute("SELECT path, size, mtime, digest_path FROM files")}
    new = sorted(p for p in disk if p not in db)
    upd = sorted(p for p in disk if p in db and (db[p][0], db[p][1]) != disk[p])
    gone = sorted(p for p in db if p not in disk)
    touched = set(new) | set(upd)
    dep = set()
    for p in touched:  # a changed/new digest changes its original's record
        if p.endswith(".digest.md"):
            orig = p[: -len(".digest.md")]
            if orig in disk and orig not in touched:
                dep.add(orig)
    by_digest = {r[0]: r[1] for r in conn.execute("SELECT digest_path, path FROM files WHERE digest_path IS NOT NULL AND path <> digest_path")}  # a digest row points at itself: skip it
    for g in gone:  # a vanished digest changes its original's record
        orig = by_digest.get(g) or (g[: -len(".digest.md")] if g.endswith(".digest.md") else None)
        if orig and orig in disk and orig not in touched:
            dep.add(orig)
    return {"disk": disk, "db_count": len(db), "new": new, "updated": upd, "dependents": sorted(dep), "gone": gone}


def run_incremental(root: Path, db_path: Path, dry: bool, today: date | None) -> dict:
    t0 = time.time()
    conn = sqlite3.connect(str(db_path), timeout=60)
    conn.isolation_level = None  # explicit BEGIN IMMEDIATE / COMMIT below
    try:
        prefixes = prefixes_from_db(conn)
        if not integrity_ok(conn):
            return {"fallback_full": True, "reason": "files/files_fts rowid mapping is not 1:1"}
        pl = plan(conn, root, prefixes)
        res = {"mode": "incremental", "scanned": len(pl["disk"]), "db_before": pl["db_count"],
               "new": len(pl["new"]), "updated": len(pl["updated"]),
               "dependents_of_changed_digests": len(pl["dependents"]), "vanished": len(pl["gone"]),
               "unindexed_top_level_folders": unindexed_top_level(root, prefixes)}
        if dry:
            res.update({"dry_run": True, "sample_new": pl["new"][:8], "sample_updated": pl["updated"][:8],
                        "sample_vanished": pl["gone"][:8], "seconds": round(time.time() - t0, 2)})
            return res

        # Read, hash and extract before the transaction opens (the slow part).
        failed: list[str] = []
        new_recs: dict[str, tuple[dict, list[dict]]] = {}
        for rel in pl["new"]:
            r = record_for(root, rel, today)
            if r is None:
                failed.append(rel)
            else:
                new_recs[rel] = r
        redo: dict[str, tuple[dict, list[dict]]] = {}
        for rel in pl["updated"] + pl["dependents"]:
            r = record_for(root, rel, today)
            if r is None:
                failed.append(rel)
            else:
                redo[rel] = r
        db_sha = {p: s for p, s in conn.execute("SELECT path, sha256 FROM files")} if pl["gone"] else {}
        moves = pair_moves({g: db_sha.get(g) for g in pl["gone"]},
                           {n: r[0].get("sha256") for n, r in new_recs.items()})
        moved_from = {a for a, _ in moves}
        moved_to = {b for _, b in moves}

        conn.execute("BEGIN IMMEDIATE")
        try:
            mg.migrate(conn, today)  # schema v2 is ensured inside this transaction (no-op when current)
            for old, new in moves:
                move_path(conn, old, new, new_recs[new], today)
            for g in pl["gone"]:
                if g not in moved_from:
                    delete_path(conn, g)
            for rel in pl["updated"] + pl["dependents"]:
                delete_path(conn, rel)
            inserted_new = 0
            for rel in pl["new"]:
                if rel in new_recs and rel not in moved_to:
                    insert_record(conn, new_recs[rel][0], new_recs[rel][1], "incremental", today)
                    inserted_new += 1
            for rel, (rec, edges) in redo.items():
                insert_record(conn, rec, edges, "incremental", today)
            mg.backfill(conn, today)  # a month that closed since the last run changes tier
            update_meta(conn, root, "incremental", {"new": inserted_new, "moved": len(moves),
                                                    "updated": len(redo), "vanished": len(pl["gone"])})
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

        res["counts"] = {"files_added": inserted_new, "files_changed": len(redo),
                         "files_removed": len(pl["gone"]) - len(moved_from), "files_moved": len(moves)}
        res["moves"] = [{"from": a, "to": b} for a, b in moves[:20]]
        res["unreadable_skipped"] = failed
        res["db_after"] = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        res["fts_rows"] = conn.execute("SELECT COUNT(*) FROM files_fts").fetchone()[0]
        res["db_matches_disk"] = res["db_after"] == len(pl["disk"]) - len(failed)
        res["seconds"] = round(time.time() - t0, 2)
        return res
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass


def run_full(root: Path, db_path: Path, keep_previous: bool, today: date | None) -> dict:
    t0 = time.time()
    prefixes = list(DEFAULT_PREFIXES)
    old_map: dict[str, tuple] = {}
    if db_path.is_file():
        try:
            c = sqlite3.connect(str(db_path), timeout=60)
            prefixes = prefixes_from_db(c)
            old_map = {p: (s, z, m) for p, s, z, m in c.execute("SELECT path, sha256, size, mtime FROM files")}
            c.close()
        except sqlite3.Error:
            pass
    tmp = db_path.with_name(f"{db_path.name}.tmp{os.getpid()}")  # unique; nothing is ever deleted
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(tmp))
    conn.executescript(SCHEMA)
    seen: set[str] = set()
    n_files = 0
    all_edges: list[dict] = []
    for prefix in prefixes:
        if not (root / prefix).exists():
            continue
        files, edges = ex.walk_prefix(root, prefix)
        for rec in files:
            if rec["path"] in seen or rec["path"] in SELF_OUTPUTS:
                continue
            seen.add(rec["path"])
            insert_record(conn, rec, [], prefix, today)
            n_files += 1
        all_edges.extend(edges)
    for p in sorted(root.iterdir()):
        if not p.is_file() or p.name.startswith(".") or p.name in seen:
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        insert_record(conn, ex.root_file_record(root, p, st), [], "(root files)", today)
        seen.add(p.name)
        n_files += 1
    insert_edges(conn, [e for e in all_edges if e.get("src") != "" and e.get("dst") != ""])
    conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?)", (mg.SCHEMA_VERSION,))
    for k, v in {"built_at": utc_now(), "vault_root": str(root), "chunk_count": str(len(prefixes) + 1),
                 "prefixes": json.dumps([[p] for p in prefixes] + ["(root files)"], ensure_ascii=False),
                 "note": "lexical catalogue and full-text search; embeddings live in vectors.db"}.items():
        conn.execute("INSERT INTO meta (key, value) VALUES (?,?)", (k, v))
    update_meta(conn, root, "full", {"files": n_files})
    conn.commit()
    carried: list[str] = []
    if db_path.is_file():
        carried = carry_over(conn, db_path)
    new_map = {p: (s, z, m) for p, s, z, m in conn.execute("SELECT path, sha256, size, mtime FROM files")}
    n_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    conn.close()
    prev = None
    if db_path.is_file():
        try:  # fold the old WAL into the old file so the replace leaves no stale sidecar
            c = sqlite3.connect(str(db_path), timeout=60)
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            c.close()
        except sqlite3.Error:
            pass
        if keep_previous:
            prev = db_path.with_name(f"vault_index_{datetime.now():%Y-%m-%d}_pre-full.db")
            n = 2
            while prev.exists():
                prev = db_path.with_name(f"vault_index_{datetime.now():%Y-%m-%d}_pre-full_v{n}.db")
                n += 1
            shutil.copy2(db_path, prev)
    tmp.replace(db_path)
    return {"mode": "full", "files": len(new_map), "edges": n_edges, "carried_tables": carried,
            "previous_db_copy": str(prev) if prev else None, "seconds": round(time.time() - t0, 2),
            "counts": counts_from_maps(old_map, new_map)}


# ----------------------------------------------------------------------------- after the file pass
def load_module(path: Path):
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(f"_index_{path.parent.name}_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def post_steps(db_path: Path, importer_file: Path | None = None, embed_file: Path | None = None,
               skip_embed: bool = False) -> dict:
    """Run the importers and the embedder if they exist. A failure is recorded, never raised.
    skip_embed leaves the embedder out (--no-embed); its vectors then stay as they were."""
    importer_file = importer_file or IMPORTER_FILE
    embed_file = embed_file or EMBED_FILE
    out: dict = {"records": None, "chunks_embedded": None, "errors": [], "notes": []}
    steps = [("importers", importer_file, "run", "records"),
             ("embed", embed_file, "embed_pending", "chunks_embedded")]
    for label, fpath, fname, key in steps:
        if label == "embed" and skip_embed:
            out["notes"].append("embed: skipped (--no-embed)")
            continue
        if not fpath.is_file():
            out["notes"].append(f"{label}: not present ({fpath.name})")
            continue
        if label == "embed" and not (HERE / ".venv" / "bin" / "python").exists():
            out["notes"].append("embed: not set up (run tools/index/embed/setup.sh); search stays keyword-only")
            continue
        try:
            fn = getattr(load_module(fpath), fname, None)
            if not callable(fn):
                raise AttributeError(f"{fpath.name} has no {fname}()")
            val = fn(str(db_path))
            out[key] = None if val is None else int(val)
        except Exception as e:  # noqa: BLE001 - a failed step is recorded in runs.errors
            out["errors"].append(f"{label}: {type(e).__name__}: {e}")
    return out


def write_run(db_path: Path, started: str, ended: str, mode: str, counts: dict | None, post: dict | None,
              extra_error: str | None = None) -> int:
    counts = counts or {}
    post = post or {}
    errors = list(post.get("errors", []))
    if extra_error:
        errors.append(extra_error)
    conn = sqlite3.connect(str(db_path), timeout=60)
    try:
        conn.execute(mg.RUNS_DDL)
        cur = conn.execute(
            "INSERT INTO runs (started, ended, mode, files_added, files_changed, files_removed, files_moved, "
            "records, chunks_embedded, errors) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (started, ended, mode, counts.get("files_added"), counts.get("files_changed"),
             counts.get("files_removed"), counts.get("files_moved"), post.get("records"),
             post.get("chunks_embedded"), "; ".join(errors) or None),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def _counts(conn: sqlite3.Connection, sql: str) -> dict:
    return {(r[0] if r[0] is not None else "(not set)"): r[1] for r in conn.execute(sql)}


def write_stats(root: Path, db_path: Path) -> Path:
    """.index/index_stats.json: counts only (per area, tier, record kind) and the last run. Never names a record."""
    out = root / ".index" / "index_stats.json"
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = set(mg.table_names(conn))
        cols = set(mg.table_columns(conn, "files"))
        try:
            rel_db = str(db_path.relative_to(root))
        except ValueError:
            rel_db = str(db_path)
        data: dict = {"generated_at": utc_now(), "db": rel_db,
                      "files_total": conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]}
        data["by_area"] = _counts(conn, "SELECT area, COUNT(*) FROM files GROUP BY area") if "area" in cols else None
        data["by_tier"] = _counts(conn, "SELECT tier, COUNT(*) FROM files GROUP BY tier") if "tier" in cols else None
        if "records" in tables:
            data["records_total"] = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
            data["records_by_kind"] = _counts(conn, "SELECT kind, COUNT(*) FROM records GROUP BY kind")
        else:
            data["records_total"] = None
            data["records_by_kind"] = None
        last = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone() if "runs" in tables else None
        data["last_run"] = dict(last) if last else None
    finally:
        conn.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, out)
    return out


def refresh_once(root: Path, db_path: Path, full: bool = False, dry: bool = False,
                 keep_previous: bool = False, today: date | None = None, skip_embed: bool = False) -> dict:
    """One complete refresh: file pass, then importers and embedder, then one runs row and the stats file."""
    started = utc_now()
    t0 = time.time()
    if dry and not db_path.is_file():
        sys.exit(f"no database to dry-run against: {db_path} (run refresh.py once without --dry-run)")
    if full or not db_path.is_file():
        res = run_full(root, db_path, keep_previous, today)
        if not full:
            res["note"] = "no DB existed: built a full one"
    else:
        res = run_incremental(root, db_path, dry, today)
        if res.get("fallback_full"):
            reason = res["reason"]
            res = run_full(root, db_path, True, today)
            res["fallback_reason"] = reason
    res["db"] = str(db_path)
    if dry:
        res["ok"] = True
        return res
    post = post_steps(db_path, skip_embed=skip_embed)
    res["post"] = post
    res["run_id"] = write_run(db_path, started, utc_now(), res["mode"], res.get("counts"), post)
    res["stats_file"] = str(write_stats(root, db_path))
    res["seconds"] = round(time.time() - t0, 2)
    res["ok"] = True
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description="Incremental (default) or full refresh of .index/vault_index.db")
    ap.add_argument("--root", default=str(brainconfig.root()))
    ap.add_argument("--db", default=None)
    ap.add_argument("--full", action="store_true", help="full rebuild (single process, atomic replace)")
    ap.add_argument("--keep-previous", action="store_true", help="with --full: copy the old DB to .index/vault_index_<date>_pre-full.db")
    ap.add_argument("--dry-run", action="store_true", help="incremental plan only; writes nothing")
    ap.add_argument("--json", action="store_true", help="print JSON only")
    ap.add_argument("--no-embed", action="store_true", help="skip the embedding step (importers still run)")
    ap.add_argument("--today", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    db_path = Path(args.db) if args.db else root / ".index" / "vault_index.db"
    today = date.fromisoformat(args.today) if args.today else None
    started = utc_now()
    mode = "full" if args.full else "incremental"
    try:
        res = refresh_once(root, db_path, full=args.full, dry=args.dry_run,
                           keep_previous=args.keep_previous, today=today, skip_embed=args.no_embed)
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "error": f"{type(e).__name__}: {e}", "db": str(db_path)}
        if not args.dry_run and db_path.is_file():
            try:
                write_run(db_path, started, utc_now(), mode, None, None, extra_error=res["error"])
            except sqlite3.Error:
                pass
        print(json.dumps(res, ensure_ascii=False, indent=2))
        log_run(root, {"at": utc_now(), **res})
        sys.exit(1)
    if not args.dry_run:
        log_run(root, {"at": utc_now(), **{k: v for k, v in res.items()
                                           if k not in ("sample_new", "sample_updated", "sample_vanished")}})
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    c = res.get("counts") or {}
    post = res.get("post") or {}
    if res["mode"] == "incremental":
        tag = "DRY-RUN " if res.get("dry_run") else ""
        line = (f"{tag}OK incremental: scanned {res['scanned']} files · new {res['new']} · updated {res['updated']} · "
                f"digest dependents {res['dependents_of_changed_digests']} · vanished {res['vanished']}")
        if not res.get("dry_run"):
            line = (f"OK incremental: scanned {res['scanned']} files · added {c['files_added']} · changed {c['files_changed']} · "
                    f"moved {c['files_moved']} · removed {c['files_removed']} · db now {res['db_after']} files "
                    f"(matches disk: {res['db_matches_disk']}) · records {post.get('records')} · "
                    f"chunks embedded {post.get('chunks_embedded')} · run #{res['run_id']}")
        print(line + f" · {res['seconds']} s")
        if post.get("errors"):
            print("  post-step errors (recorded in runs.errors): " + "; ".join(post["errors"]))
        if res.get("unindexed_top_level_folders"):
            print("  top-level folders not in the index (add to DEFAULT_PREFIXES if they should be): "
                  + ", ".join(res["unindexed_top_level_folders"]))
        if res.get("dry_run"):
            for k in ("sample_new", "sample_updated", "sample_vanished"):
                if res[k]:
                    print(f"  {k}: {res[k]}")
    else:
        print(f"OK full rebuild: {res['files']} files · {res['edges']} edges · added {c.get('files_added')} · "
              f"moved {c.get('files_moved')} · removed {c.get('files_removed')} · carried {', '.join(res['carried_tables']) or 'none'} · "
              f"{res['seconds']} s · run #{res.get('run_id')}"
              + (f" · previous DB copied to {res['previous_db_copy']}" if res.get("previous_db_copy") else ""))
        if post.get("errors"):
            print("  post-step errors (recorded in runs.errors): " + "; ".join(post["errors"]))


if __name__ == "__main__":
    main()
