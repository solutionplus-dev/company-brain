#!/usr/bin/env python3
"""Walk one vault prefix and write a catalog chunk (JSON). Stdlib only.

Does not invent purpose. Digest text is copied when a sibling .digest.md exists.
Identity/residency paths are catalogued as metadata only — contents are not read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import brainconfig

SKIP_DIRS = {
    ".git",
    "graphify-out",
    ".index",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "_chunks",
    ".cursor",
    ".claude",
    ".agents",
    ".codex",
    ".muse",
    "_ocr_tmp",
    "_secrets",
    "credentials",
}
SKIP_FILE_PREFIX = "."
HASH_MAX = 32 * 1024 * 1024
DIGEST_TEXT_MAX = 16_384
PURPOSE_MAX = 280
PII_NAME = re.compile(
    r"(passport|visa|medical|national id|id[ _-]?card|residence|permit)", re.I
)
YM_FOLDER = re.compile(r"^(?:(\d{4})[-/](\d{2})|(\d{4}))$")
YM_FILE = re.compile(r"(?:^|_)(\d{4})-(\d{2})(?:-\d{2})?(?:_|$|\.)")

CONTENT_EXTS = {".md", ".txt", ".digest.md"}  # .digest.md handled via suffix
TEXT_EXTS = {".md", ".txt", ".csv", ".json", ".html", ".vtt"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def should_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or name.startswith(".")


def rel_to(root: Path, path: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def entity_of(rel: str) -> str:
    top = rel.split("/", 1)[0]
    return brainconfig.label_by_top().get(top, "Vault")


def kind_of(rel: str, name: str, ext: str) -> str:
    lower = rel.lower()
    n = name.lower()
    if n.endswith(".digest.md"):
        return "digest"
    if n == "summary.md":
        return "summary"
    if n == "manifest.md":
        return "manifest"
    if n == "transcript.md":
        return "transcript"
    if n == "notes.md":
        return "notes"
    if "/identity/" in "/" + lower:
        return "identity-excluded"
    if "/invoices/" in lower or n.startswith("inv-"):
        return "invoice"
    if "/expenses/" in lower:
        return "expense"
    if "/attachments/" in lower:
        return "email-attachment"
    if "/02_meetings/" in lower:
        return "meeting-file"
    if ext in {".pdf", ".docx", ".doc"}:
        return "document"
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return "image"
    if ext in {".mp4", ".m4a", ".m4v"}:
        return "media"
    if ext in {".xlsx", ".xls", ".csv"}:
        return "spreadsheet"
    if ext == ".eml":
        return "email"
    if ext == ".md":
        return "note"
    if ext == ".json":
        return "json"
    return "file"


def year_month_of(rel: str, name: str) -> str | None:
    m = YM_FILE.search(name)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    for part in rel.split("/"):
        fm = YM_FOLDER.match(part)
        if fm:
            if fm.group(1) and fm.group(2):
                return f"{fm.group(1)}-{fm.group(2)}"
    return None


def residency_or_pii(rel: str, name: str) -> bool:
    lower = rel.lower()
    if "/identity/" in "/" + lower:
        return True
    if "/credentials/" in "/" + lower or "/_secrets/" in "/" + lower:
        return True
    if PII_NAME.search(name):
        return True
    return False


def sha256_file(path: Path, size: int) -> str | None:
    if size > HASH_MAX:
        return None
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            while True:
                block = f.read(1024 * 1024)
                if not block:
                    break
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


def read_text_capped(path: Path, cap: int) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:1024]:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    text = text.replace("\x00", "")
    if len(text) > cap:
        text = text[:cap]
    return text


def purpose_from_digest(text: str) -> str | None:
    """First useful line from a digest. Never guesses beyond what the digest wrote."""
    lines = [ln.strip() for ln in text.splitlines()]
    skip_heads = {"what it is", "purpose", "summary"}
    for i, ln in enumerate(lines):
        low = ln.lower().rstrip(":")
        if low in skip_heads and i + 1 < len(lines) and lines[i + 1]:
            candidate = lines[i + 1]
            if candidate.startswith("#") or candidate.startswith("|"):
                continue
            return candidate[:PURPOSE_MAX]
        if ln.startswith("# ") and not ln.lower().startswith("# digest"):
            body = ln[2:].strip()
            if body:
                return body[:PURPOSE_MAX]
    for ln in lines:
        if ln and not ln.startswith("#") and not ln.startswith("---") and not ln.startswith("|"):
            return ln[:PURPOSE_MAX]
    return None


def digest_path_for(root: Path, path: Path) -> Path | None:
    sibling = Path(str(path) + ".digest.md")
    if sibling.is_file():
        return sibling
    if path.name.endswith(".digest.md"):
        return path
    return None


def file_record(root: Path, path: Path, st) -> tuple[dict, list[dict]]:
    """Catalog record (+ its edges) for one file. Shared by walk_prefix and tools/index/refresh.py."""
    fn = path.name
    rel = rel_to(root, path)
    ext = path.suffix.lower()
    if fn.endswith(".digest.md"):
        ext = ".digest.md"
    blocked = residency_or_pii(rel, fn)
    digest = None if blocked else digest_path_for(root, path)
    digest_rel = rel_to(root, digest) if digest else None
    digest_text = None
    purpose = None
    if digest and digest.is_file() and not blocked:
        digest_text = read_text_capped(digest, DIGEST_TEXT_MAX)
        if digest_text:
            purpose = purpose_from_digest(digest_text)
    if not blocked and not digest_text and ext in TEXT_EXTS:
        digest_text = read_text_capped(path, DIGEST_TEXT_MAX)
        if purpose is None and digest_text:
            purpose = purpose_from_digest(digest_text)
    rec = {
        "path": rel,
        "name": fn,
        "ext": ext,
        "size": int(st.st_size),
        "mtime": int(st.st_mtime),
        "sha256": None if blocked else sha256_file(path, st.st_size),
        "entity": entity_of(rel),
        "folder": rel.rsplit("/", 1)[0] if "/" in rel else "",
        "kind": kind_of(rel, fn, ext),
        "year_month": year_month_of(rel, fn),
        "source": "digest" if digest_rel and not rel.endswith(".digest.md") else "original",
        "certainty": "digest" if purpose else "unknown",
        "purpose": purpose,
        "digest_path": digest_rel,
        "summary_ref": None,
        "git_tracked": None,
        "digest_text": digest_text,
    }
    edges: list[dict] = []
    parent = rec["folder"]
    if parent:
        edges.append({"src": rel, "dst": parent, "rel": "in_folder"})
    if digest_rel and digest_rel != rel:
        edges.append({"src": digest_rel, "dst": rel, "rel": "digest_of"})
    return rec, edges


def root_file_record(root: Path, p: Path, st) -> dict:
    """Catalog record for a file sitting directly on the vault root (no digest sibling, no edges)."""
    rel = p.name
    ext = p.suffix.lower()
    blocked = residency_or_pii(rel, p.name)
    digest_text = None
    purpose = None
    if not blocked and ext in TEXT_EXTS:
        digest_text = read_text_capped(p, DIGEST_TEXT_MAX)
        if digest_text:
            purpose = purpose_from_digest(digest_text)
    return {
        "path": rel,
        "name": p.name,
        "ext": ext,
        "size": int(st.st_size),
        "mtime": int(st.st_mtime),
        "sha256": None if blocked else sha256_file(p, st.st_size),
        "entity": "Vault",
        "folder": "",
        "kind": "identity-excluded" if blocked else kind_of(rel, p.name, ext),
        "year_month": year_month_of(rel, p.name),
        "source": "original",
        "certainty": "digest" if purpose else "unknown",
        "purpose": purpose,
        "digest_path": None,
        "summary_ref": None,
        "git_tracked": None,
        "digest_text": digest_text,
    }


def walk_prefix(root: Path, prefix: str) -> tuple[list[dict], list[dict]]:
    base = root / prefix if prefix not in (".", "") else root
    if not base.exists():
        raise SystemExit(f"prefix does not exist: {prefix}")
    files: list[dict] = []
    edges: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if not should_skip_dir(d))
        for fn in sorted(filenames):
            if fn.startswith(SKIP_FILE_PREFIX):
                continue
            path = Path(dirpath) / fn
            if not path.is_file() or brainconfig.ignored(rel_to(root, path), root):
                continue
            try:
                st = path.stat()
            except OSError:
                continue
            rec, e = file_record(root, path, st)
            files.append(rec)
            edges.extend(e)
    return files, edges


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract one vault catalog chunk")
    ap.add_argument("--root", default=str(brainconfig.root()))
    ap.add_argument("--prefix", action="append", default=[], help="Vault-relative folder (repeatable)")
    ap.add_argument("--out", required=True, help="JSON output path")
    ap.add_argument("--chunk-id", required=True)
    ap.add_argument("--include-root-files", action="store_true", help="Also catalog files sitting on the vault root")
    ap.add_argument("--root-files-only", action="store_true", help="Catalog only files on the vault root")
    args = ap.parse_args()
    if args.root_files_only:
        args.include_root_files = True
    if not args.prefix and not args.root_files_only:
        sys.exit("need --prefix or --root-files-only")
    root = Path(args.root).resolve()
    files: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()
    for prefix in args.prefix:
        chunk_files, chunk_edges = walk_prefix(root, prefix)
        for rec in chunk_files:
            if rec["path"] in seen:
                continue
            seen.add(rec["path"])
            files.append(rec)
        edges.extend(chunk_edges)
    if args.include_root_files:
        for p in sorted(root.iterdir()):
            if not p.is_file() or p.name.startswith("."):
                continue
            rel = p.name
            if rel in seen:
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            files.append(root_file_record(root, p, st))
            seen.add(rel)
    payload = {
        "chunk_id": args.chunk_id,
        "prefix": args.prefix if args.prefix else "(root files)",
        "root": str(root),
        "built_at": utc_now(),
        "file_count": len(files),
        "edge_count": len(edges),
        "files": files,
        "edges": edges,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=None) + "\n", encoding="utf-8")
    tmp.replace(out)
    print(
        f"OK chunk={args.chunk_id} prefix={args.prefix} "
        f"files={len(files)} edges={len(edges)} -> {out}"
    )


if __name__ == "__main__":
    main()
