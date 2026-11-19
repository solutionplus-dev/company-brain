#!/usr/bin/env python3
"""Idempotent schema migration for the vault catalog, .index/vault_index.db. Stdlib only.

Adds to `files`: tier, area, doc_date, has_digest. sha256 and digest_path already exist and are added only when
missing. Creates `records` (one row per business object; filled by tools/index/importers/) and `runs` (one row per
refresh), with their indexes. Backfills the derived columns from each row's path and digest_path (no disk reads).

  python3 tools/index/migrate.py                    migrate .index/vault_index.db
  python3 tools/index/migrate.py --db PATH          migrate another file (test copies)
  python3 tools/index/migrate.py --backup-to PATH   copy the database to PATH first (never overwrites)

Safe to run twice: the second run adds no column and backfills no row. build_index.py creates the same schema on a
fresh build.

Derivation rules:
  tier       archive  a folder named _archive or ARCHIVE anywhere in the path
             month    a folder YYYY-MM for a month before the current month
             year     a folder YYYY for a year before the current year
             current  everything else
  area       by the first path segment: an entity's folder (brain.config.json) -> finance-<code>;
             finance -> finance; 01_Clients -> clients; 02_Meetings -> meetings; 03_Sales -> sales;
             04_Marketing -> marketing; 05_Operations -> operations; 00_Brain -> brain; tools, scripts -> system
  doc_date   YYYY-MM-DD when the file name carries a full date, else YYYY-MM from year_month, else NULL
  has_digest 1 when digest_path names a different file (an original with its digest), else 0
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

import brainconfig

SCHEMA_VERSION = "2"

# (column, type). The first list is new; the second is present in every build since the first, added only if missing.
NEW_FILE_COLUMNS = [("tier", "TEXT"), ("area", "TEXT"), ("doc_date", "TEXT"), ("has_digest", "INTEGER")]
EXISTING_FILE_COLUMNS = [("sha256", "TEXT"), ("digest_path", "TEXT")]

RECORDS_DDL = """CREATE TABLE IF NOT EXISTS records(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, company TEXT, ref TEXT, title TEXT,
  date TEXT, due_date TEXT, amount REAL, amount_text TEXT, currency TEXT,
  counterparty TEXT, status TEXT, certainty TEXT, client TEXT,
  source_path TEXT NOT NULL, source_line INTEGER, extra TEXT, imported_at TEXT,
  UNIQUE(kind, ref, source_path, source_line))"""

RUNS_DDL = """CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY, started TEXT, ended TEXT, mode TEXT,
  files_added INTEGER, files_changed INTEGER, files_removed INTEGER, files_moved INTEGER,
  records INTEGER, chunks_embedded INTEGER, errors TEXT)"""

RECORDS_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_records_kind ON records(kind, company, status)",
    "CREATE INDEX IF NOT EXISTS idx_records_due ON records(due_date)",
]
FILES_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_files_tier ON files(tier)",
    "CREATE INDEX IF NOT EXISTS idx_files_area ON files(area)",
]

AREA_BY_TOP = brainconfig.area_by_top()
ROOT_SYSTEM_EXTS = {".md", ".html", ".py", ".sh", ".js", ".json", ".txt"}
MONTH_DIR = re.compile(r"\d{4}-\d{2}")
YEAR_DIR = re.compile(r"\d{4}")
FULL_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")


def area_of(rel: str) -> str:
    parts = rel.split("/")
    if len(parts) == 1:
        return "system" if Path(rel).suffix.lower() in ROOT_SYSTEM_EXTS else "other"
    return AREA_BY_TOP.get(parts[0], "other")


def tier_of(rel: str, today: date | None = None) -> str:
    today = today or date.today()
    folders = rel.split("/")[:-1]
    if "_archive" in folders or "ARCHIVE" in folders:
        return "archive"
    for f in folders:
        if MONTH_DIR.fullmatch(f):
            y, m = int(f[:4]), int(f[5:])
            if 1 <= m <= 12 and (y, m) < (today.year, today.month):
                return "month"
    for f in folders:
        if YEAR_DIR.fullmatch(f) and int(f) < today.year:
            return "year"
    return "current"


def doc_date_of(name: str, year_month: str | None) -> str | None:
    m = FULL_DATE.search(name or "")
    if m:
        try:
            date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        except ValueError:
            pass  # not a real date: fall through to the month
    return year_month or None


def derive_fields(rec: dict, today: date | None = None) -> dict:
    """tier, area, doc_date, has_digest for one catalog record. Pure function of path, name, year_month, digest_path."""
    rel = rec["path"]
    name = rec.get("name") or rel.rsplit("/", 1)[-1]
    digest = rec.get("digest_path")
    return {
        "tier": tier_of(rel, today),
        "area": area_of(rel),
        "doc_date": doc_date_of(name, rec.get("year_month")),
        "has_digest": 1 if digest and digest != rel else 0,
    }


def table_names(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]


def backfill(conn: sqlite3.Connection, today: date | None = None) -> int:
    """Recompute the derived columns of every row; write only the rows that differ. Returns rows changed."""
    rows = conn.execute(
        "SELECT rowid, path, name, year_month, digest_path, tier, area, doc_date, has_digest FROM files"
    ).fetchall()
    changed = []
    for rid, path, name, ym, dig, tier, area, dd, hd in rows:
        d = derive_fields({"path": path, "name": name, "year_month": ym, "digest_path": dig}, today)
        if (d["tier"], d["area"], d["doc_date"], d["has_digest"]) != (tier, area, dd, hd):
            changed.append((d["tier"], d["area"], d["doc_date"], d["has_digest"], rid))
    if changed:
        conn.executemany("UPDATE files SET tier=?, area=?, doc_date=?, has_digest=? WHERE rowid=?", changed)
    return len(changed)


def migrate(conn: sqlite3.Connection, today: date | None = None) -> dict:
    """Bring an existing catalog to schema version 2. Runs in one transaction unless the caller already has one."""
    report = {"added_columns": [], "present_columns": [], "created_tables": [], "backfilled": 0,
              "schema_version": SCHEMA_VERSION}
    own_tx = not conn.in_transaction
    if own_tx:
        conn.execute("BEGIN IMMEDIATE")
    try:
        cols = table_columns(conn, "files")
        if not cols:
            raise RuntimeError("no files table: build the index first (tools/index/build_index.py)")
        for name, typ in NEW_FILE_COLUMNS + EXISTING_FILE_COLUMNS:
            if name in cols:
                report["present_columns"].append(name)
            else:
                conn.execute(f"ALTER TABLE files ADD COLUMN {name} {typ}")
                report["added_columns"].append(name)
        before = set(table_names(conn))
        conn.execute(RECORDS_DDL)
        conn.execute(RUNS_DDL)
        for ddl in RECORDS_INDEX_DDL + FILES_INDEX_DDL:
            conn.execute(ddl)
        report["created_tables"] = sorted(set(table_names(conn)) - before)
        report["backfilled"] = backfill(conn, today)
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (SCHEMA_VERSION,),
        )
    except BaseException:
        if own_tx:
            conn.execute("ROLLBACK")
        raise
    else:
        if own_tx:
            conn.execute("COMMIT")
    return report


def backup(src: Path, dst: Path) -> None:
    """Consistent copy with the SQLite backup API. Refuses to overwrite an existing file."""
    if dst.exists():
        raise FileExistsError(f"refusing to overwrite {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Idempotent migration of .index/vault_index.db to schema v2")
    ap.add_argument("--db", default=None)
    ap.add_argument("--backup-to", default=None, help="copy the database here first (never overwrites)")
    ap.add_argument("--today", default=None, help="YYYY-MM-DD; default today (for tests)")
    args = ap.parse_args()
    root = brainconfig.root()
    db = Path(args.db) if args.db else root / ".index" / "vault_index.db"
    if not db.is_file():
        sys.exit(f"no database: {db}")
    today = date.fromisoformat(args.today) if args.today else None
    if args.backup_to:
        backup(db, Path(args.backup_to))
        print(f"backup: {args.backup_to}")
    conn = sqlite3.connect(str(db), timeout=60)
    conn.isolation_level = None
    try:
        report = migrate(conn, today)
    finally:
        conn.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
