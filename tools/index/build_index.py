#!/usr/bin/env python3
"""Merge catalog chunks into a SQLite FTS5 index. Derived; rebuildable. Stdlib only.

Schema v2: files gains tier, area, doc_date, has_digest; tables records and runs exist.
The DDL for those lives in migrate.py, so a fresh build and a migrated database agree.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
import os
from pathlib import Path

from migrate import (  # noqa: E402  (same directory; stdlib only)
    FILES_INDEX_DDL,
    RECORDS_DDL,
    RECORDS_INDEX_DDL,
    RUNS_DDL,
    SCHEMA_VERSION,
    derive_fields,
)

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE files (
  path TEXT PRIMARY KEY,
  name TEXT,
  ext TEXT,
  size INTEGER,
  mtime INTEGER,
  sha256 TEXT,
  entity TEXT,
  folder TEXT,
  kind TEXT,
  year_month TEXT,
  source TEXT,
  certainty TEXT,
  purpose TEXT,
  digest_path TEXT,
  summary_ref TEXT,
  git_tracked INTEGER,
  chunk_id TEXT,
  tier TEXT,
  area TEXT,
  doc_date TEXT,
  has_digest INTEGER
);

CREATE VIRTUAL TABLE files_fts USING fts5(
  path,
  name,
  purpose,
  digest_text,
  entity,
  tokenize='unicode61'
);

CREATE TABLE edges (
  src TEXT NOT NULL,
  dst TEXT NOT NULL,
  rel TEXT NOT NULL
);

CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE INDEX idx_files_entity ON files(entity);
CREATE INDEX idx_files_ext ON files(ext);
CREATE INDEX idx_files_ym ON files(year_month);
CREATE INDEX idx_files_kind ON files(kind);
CREATE INDEX idx_edges_src ON edges(src);
CREATE INDEX idx_edges_dst ON edges(dst);
""" + "".join(f"{stmt};\n" for stmt in [RECORDS_DDL, RUNS_DDL, *RECORDS_INDEX_DDL, *FILES_INDEX_DDL])

FILE_COLS = [
    "path", "name", "ext", "size", "mtime", "sha256", "entity", "folder",
    "kind", "year_month", "source", "certainty", "purpose", "digest_path",
    "summary_ref", "git_tracked", "chunk_id", "tier", "area", "doc_date", "has_digest",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def git_head(root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def load_chunks(chunks_dir: Path) -> list[dict]:
    paths = [p for p in sorted(chunks_dir.glob("*.json")) if not p.name.startswith(".")]
    named = [p for p in paths if not p.stem.isdigit()]
    # Prefer named prefixes (00_Brain.json) over leftover two-digit extracts (01.json).
    use = named if named else paths
    chunks = []
    for p in use:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            sys.exit(f"INVALID JSON in {p}: {e}")
        if "files" not in data:
            sys.exit(f"chunk missing files[]: {p}")
        chunks.append(data)
    return chunks


def main() -> None:
    ap = argparse.ArgumentParser(description="Build vault_index.db from chunks")
    ap.add_argument("--root", default=os.environ.get("BRAIN_ROOT") or str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--chunks-dir", default=None)
    ap.add_argument("--db", default=None)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    chunks_dir = Path(args.chunks_dir) if args.chunks_dir else root / "tools" / "index" / "_chunks"
    db_path = Path(args.db) if args.db else root / ".index" / "vault_index.db"
    if not chunks_dir.is_dir():
        sys.exit(f"no chunks dir: {chunks_dir}")
    chunks = load_chunks(chunks_dir)
    if not chunks:
        sys.exit(f"no chunk JSON in {chunks_dir}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".db.tmp")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(str(tmp))
    conn.executescript(SCHEMA)
    seen: set[str] = set()
    n_files = 0
    n_edges = 0
    n_purpose = 0
    prefixes = []
    for ch in chunks:
        cid = str(ch.get("chunk_id") or "")
        prefixes.append(ch.get("prefix") or cid)
        for rec in ch.get("files", []):
            path = rec.get("path")
            if not path or path in seen:
                continue
            seen.add(path)
            rec.update(derive_fields(rec))
            row = {k: rec.get(k) for k in FILE_COLS}
            row["chunk_id"] = cid
            conn.execute(
                f"INSERT INTO files ({','.join(FILE_COLS)}) VALUES ({','.join('?' * len(FILE_COLS))})",
                [row[k] for k in FILE_COLS],
            )
            conn.execute(
                "INSERT INTO files_fts (path, name, purpose, digest_text, entity) VALUES (?,?,?,?,?)",
                [
                    path,
                    rec.get("name") or "",
                    rec.get("purpose") or "",
                    rec.get("digest_text") or "",
                    rec.get("entity") or "",
                ],
            )
            n_files += 1
            if rec.get("purpose"):
                n_purpose += 1
        for e in ch.get("edges", []):
            src, dst, rel = e.get("src"), e.get("dst"), e.get("rel")
            if not (src and dst and rel):
                continue
            conn.execute(
                "INSERT INTO edges (src, dst, rel) VALUES (?,?,?)",
                (src, dst, rel),
            )
            n_edges += 1

    meta = {
        "schema_version": SCHEMA_VERSION,
        "built_at": utc_now(),
        "vault_root": str(root),
        "git_head": git_head(root),
        "file_count": str(n_files),
        "edge_count": str(n_edges),
        "purpose_count": str(n_purpose),
        "chunk_count": str(len(chunks)),
        "prefixes": json.dumps(prefixes, ensure_ascii=False),
        "note": "lexical catalogue and full-text search; embeddings live in vectors.db",
    }
    for k, v in meta.items():
        conn.execute("INSERT INTO meta (key, value) VALUES (?,?)", (k, v))
    conn.commit()
    conn.close()
    tmp.replace(db_path)
    print(
        f"OK db={db_path} files={n_files} edges={n_edges} "
        f"with_purpose={n_purpose} chunks={len(chunks)}"
    )


if __name__ == "__main__":
    main()
