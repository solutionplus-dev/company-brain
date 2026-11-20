#!/usr/bin/env python3
"""Vault embedding lane: chunk the catalogue's text, embed it, search it.

Model: EmbeddingGemma 2 (mlx-community/embeddinggemma-2-4bit, affine 4-bit), run by
mlx-vlm's embedding loader (mean pooling, L2-normalised, 768 dimensions). Settings:
embed_config.json.

Storage (.index/vectors.db), content-addressed:
  chunks     (sha256, ord, text, n_chars)        sha256 = sha256 of the embedded text
  vectors    (sha256, ord, bin, full, model)     bin = sign bit per dimension (96 bytes),
                                                 full = unit vector for re-scoring
  file_map   (path, sha256, ...)                 catalogue path -> content key, refreshed each run
  embed_runs one row per run

Usage:
  python3 tools/index/embed/embed.py pending [--index-db PATH] [--limit N] [--dry-run]
  python3 tools/index/embed/embed.py search "<question>" [-k 20] [--exact] [--json]
  python3 tools/index/embed/embed.py stats
  python3 tools/index/embed/embed.py selftest

Public functions (callable from the system python3; when the heavy libraries are
missing they re-launch this file inside tools/index/.venv):
  embed_pending(index_db_path, limit=None, dry_run=False) -> int   chunks embedded
  search(index_db_path, query, k=20, exact=False) -> list[dict]
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import html
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]  # tools/index/embed -> repository root (code, venv, model)
ROOT = Path(os.environ.get("BRAIN_ROOT") or REPO).resolve()  # the brain whose files are embedded
INDEX_DIR = ROOT / ".index"
VECTORS_DB = INDEX_DIR / "vectors.db"
DEFAULT_INDEX_DB = INDEX_DIR / "vault_index.db"
VENV_PY = REPO / "tools" / "index" / ".venv" / "bin" / "python"
CONFIG_PATH = HERE / "embed_config.json"
LOCK_PATH = INDEX_DIR / "embed.lock"
RESULT_TAG = "EMBED_RESULT_JSON:"
CHILD_ENV = "VAULT_EMBED_CHILD"

sys.path.insert(0, str(HERE))
from redact import REDACT_VERSION, redact  # noqa: E402  (same folder)

CFG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
DIM = int(CFG["dimension"])
BIN_BYTES = DIM // 8
MODEL_ID = (
    f"embeddinggemma-2-4bit@{CFG['model']['revision'][:8]}"
    f"|mlx-vlm@{CFG['runtime']['mlx_vlm_commit'][:8]}|mean-normalised|{CFG['storage']['full_format']}"
    f"|{REDACT_VERSION}"
)

# Text extensions come from the existing extractor (reused, not edited) plus the config.
sys.path.insert(0, str(REPO / "tools" / "index"))
import extract_chunk as xc  # noqa: E402  (stdlib only)

TEXT_EXTS = set(xc.TEXT_EXTS) | set(CFG["exclusions"]["text_extensions"])

IDENTITY_TOKENS = (
    "passport", "visa", "reisepass", "aufenthalt", "ausweis",
    "credential", "recoverycode", "recovery_code", "recovery code", "recovery-code",
    "keystore", "identity/", "credentials/",
)
SECRET_SUFFIXES = {".pfx", ".pem", ".key", ".p12", ".jks", ".keystore"}
EXTRA_NAME_TOKENS = (
    "freischaltung", "aktivierungscode", "legitimierungs", "activation code", ".pfx",
    "medical report", "patient", "payslip",
)
EXTRA_NAME_REGEX = re.compile(r"(?<![a-z])(id card|id badge|business card)(?![a-z])")
GUARD_TOKENS = tuple(CFG["exclusions"]["path_prefix_name_pattern"]["name_contains"])
GUARD_PREFIX = CFG["exclusions"]["path_prefix_name_pattern"]["prefix"].lower()


def log(msg: str) -> None:
    sys.stderr.write(time.strftime("%H:%M:%S ") + msg + "\n")
    sys.stderr.flush()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ----------------------------------------------------------------- venv bridge

def _heavy_ready() -> bool:
    try:
        import numpy  # noqa: F401
        import pathspec  # noqa: F401
        import mlx.core  # noqa: F401
        import mlx_vlm.embedding_loader  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return False
    return True


def _relaunch(op: str, kwargs: dict):
    """Run one operation in tools/index/.venv and return its JSON result."""
    if os.environ.get(CHILD_ENV) == "1":
        raise RuntimeError("heavy libraries missing inside tools/index/.venv; run tools/index/embed/setup.sh")
    if not VENV_PY.exists():
        raise RuntimeError(f"venv missing at {VENV_PY}; run tools/index/embed/setup.sh")
    env = dict(os.environ)
    env[CHILD_ENV] = "1"
    cmd = [str(VENV_PY), str(HERE / "embed.py"), "_call", op, json.dumps(kwargs)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=None, text=True, env=env)
    result = None
    for line in proc.stdout.splitlines():
        if line.startswith(RESULT_TAG):
            result = json.loads(line[len(RESULT_TAG):])
        elif line.strip():
            sys.stderr.write(line + "\n")
    if result is None:
        raise RuntimeError(f"embed child exited {proc.returncode} without a result")
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "embed child failed"))
    return result["result"]


# ----------------------------------------------------------------- storage

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
  sha256 TEXT NOT NULL,
  ord INTEGER NOT NULL,
  text TEXT NOT NULL,
  n_chars INTEGER NOT NULL,
  PRIMARY KEY (sha256, ord)
);
CREATE TABLE IF NOT EXISTS vectors (
  sha256 TEXT NOT NULL,
  ord INTEGER NOT NULL,
  bin BLOB NOT NULL,
  full BLOB NOT NULL,
  model TEXT NOT NULL,
  PRIMARY KEY (sha256, ord)
);
CREATE TABLE IF NOT EXISTS file_map (
  path TEXT PRIMARY KEY,
  sha256 TEXT NOT NULL,
  file_sha256 TEXT,
  src_path TEXT,
  src_size INTEGER,
  src_mtime INTEGER
);
CREATE INDEX IF NOT EXISTS idx_file_map_sha ON file_map(sha256);
CREATE TABLE IF NOT EXISTS embed_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT,
  finished_at TEXT,
  model TEXT,
  index_db TEXT,
  catalogue_files INTEGER,
  eligible_files INTEGER,
  keys_new INTEGER,
  chunks_new INTEGER,
  chunks_total INTEGER,
  seconds REAL,
  excluded_json TEXT,
  no_text INTEGER,
  errors INTEGER,
  notes TEXT
);
"""


def _open_vectors(readonly: bool = False) -> sqlite3.Connection:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(VECTORS_DB), timeout=60)
    con.executescript(SCHEMA)
    return con


def _catalogue_rows(index_db: Path) -> list[tuple[str, str | None]]:
    uri = f"file:{Path(index_db).resolve()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=60)
    try:
        return con.execute("SELECT path, sha256 FROM files ORDER BY path").fetchall()
    finally:
        con.close()


# ----------------------------------------------------------------- exclusions

def _graph_spec():
    import pathspec
    lines = (ROOT / ".brainignore").read_text(encoding="utf-8").splitlines()
    return pathspec.GitIgnoreSpec.from_lines(lines)


def exclusion_reason(rel: str, spec) -> str | None:
    """Why a catalogue path must never be embedded, or None."""
    low = rel.lower()
    name = low.rsplit("/", 1)[-1]
    if spec.match_file(rel):
        return "brainignore"
    if any(tok in low for tok in IDENTITY_TOKENS):
        return "identity-residency-credentials"
    if "_archive/" in low or low.startswith("repos/"):
        return "archive-or-repos"
    if re.search(r"(^|/)\.env(\.|$)", low) or name == ".mcp.json":
        return "secrets-config"
    if Path(name).suffix in SECRET_SUFFIXES:
        return "secrets-config"
    if GUARD_PREFIX and low.startswith(GUARD_PREFIX) and any(tok in low for tok in GUARD_TOKENS):
        return "guarded-folder-name-pattern"
    if any(tok in low for tok in EXTRA_NAME_TOKENS) or EXTRA_NAME_REGEX.search(low):
        return "name-excluded-private-scan"
    if "/_ocr_tmp/" in "/" + low:
        return "ocr-scratch"
    return None


# ----------------------------------------------------------------- text

def _strip_html(s: str) -> str:
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"[ \t]+", " ", html.unescape(s))


def _eml_text(raw: bytes) -> str:
    from email import policy
    from email.parser import BytesParser
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    parts = []
    for part in msg.walk():
        if part.is_multipart() or part.get_filename():
            continue
        ctype = part.get_content_type()
        try:
            if ctype == "text/plain":
                parts.append(part.get_content())
            elif ctype == "text/html":
                parts.append(_strip_html(part.get_content()))
        except Exception:  # undecodable part: skip it, keep the rest
            continue
    head = [f"{h}: {msg.get(h)}" for h in ("Subject", "From", "Date") if msg.get(h)]
    return ("\n".join(head) + "\n\n" + "\n\n".join(parts)).strip()


def _text_source(rel: str) -> Path | None:
    """The file whose text represents this catalogue entry, or None (no text)."""
    p = ROOT / rel
    name = p.name.lower()
    ext = ".digest.md" if name.endswith(".digest.md") else p.suffix.lower()
    if ext in TEXT_EXTS:
        return p if p.is_file() else None
    digest = xc.digest_path_for(ROOT, p)  # sibling <name>.digest.md, if any
    return digest if digest and digest.is_file() else None


def _read_source_text(src: Path) -> str | None:
    raw = src.read_bytes()
    if b"\x00" in raw[:8192]:
        return None
    name = src.name.lower()
    if name.endswith(".eml"):
        text = _eml_text(raw)
    else:
        text = raw.decode("utf-8", errors="replace")
        if name.endswith((".html", ".htm")):
            text = _strip_html(text)
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return text or None


def _split_long(p: str, size: int, overlap: int) -> list[str]:
    out: list[str] = []
    n = len(p)
    start = 0
    while start < n:
        end = min(start + size, n)
        if end < n:
            cut = p.rfind(" ", start + size // 2, end)
            if cut > start:
                end = cut
        piece = p[start:end].strip()
        if piece:
            out.append(piece)
        if end >= n:
            break
        nxt = max(end - overlap, start + 1)
        sp = p.find(" ", nxt, end)
        start = sp + 1 if sp != -1 else nxt
    return out


def _tail(text: str, overlap: int) -> str:
    if len(text) <= overlap:
        return text
    t = text[-overlap:]
    sp = t.find(" ")
    return t[sp + 1:] if sp != -1 else t


def chunk_text(text: str, size: int | None = None, overlap: int | None = None) -> list[str]:
    """About 1,200-character chunks with 150 characters of overlap, cut on paragraph boundaries."""
    size = size or int(CFG["chunking"]["chars"])
    overlap = overlap if overlap is not None else int(CFG["chunking"]["overlap"])
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for p in paras:
        if len(p) <= size:
            pieces.append(p)
        else:
            pieces.extend(_split_long(p, size, overlap))
    chunks: list[str] = []
    cur = ""
    for p in pieces:
        if not cur:
            cur = p
            continue
        if len(cur) + 2 + len(p) <= size:
            cur = cur + "\n\n" + p
            continue
        chunks.append(cur)
        tail = _tail(cur, overlap)
        cand = (tail + "\n\n" + p) if tail else p
        cur = cand if len(cand) <= size else p
    if cur:
        chunks.append(cur)
    return chunks


def content_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------- model

_MODEL = None  # (mlx model, tokenizer)


def _load_model():
    global _MODEL
    if _MODEL is None:
        from mlx_vlm.embedding_loader import load_embedding_model
        from transformers import AutoTokenizer
        path = REPO / CFG["model"]["local_dir"]
        if not (path / CFG["model"]["weights_file"]).exists():
            raise RuntimeError(f"model files missing in {path}; run tools/index/embed/setup.sh")
        model = load_embedding_model(path)
        tokenizer = AutoTokenizer.from_pretrained(str(path))
        _MODEL = (model, tokenizer)
    return _MODEL


def _embed_strings(texts: list[str]):
    """Unit-length float32 vectors, one row per text (pooling and normalising are in the model)."""
    import mlx.core as mx
    import numpy as np
    model, tok = _load_model()
    bs = int(CFG["runtime"]["batch_size"])
    max_len = int(CFG["runtime"]["max_length"])
    out = []
    for i in range(0, len(texts), bs):
        batch = texts[i:i + bs]
        inputs = tok(batch, padding=True, truncation=True, max_length=max_len, return_tensors="np")
        emb = model(**{k: mx.array(v) for k, v in inputs.items()}).text_embeds
        out.append(np.array(emb, dtype=np.float32))
    arr = np.concatenate(out, axis=0)
    if arr.shape[1] != DIM:
        raise RuntimeError(f"model returned dimension {arr.shape[1]}, expected {DIM}")
    if not np.all(np.isfinite(arr)):
        raise RuntimeError("model returned non-finite values")
    arr /= np.maximum(np.linalg.norm(arr, axis=1, keepdims=True), 1e-12)
    return arr


def embed_documents(texts: list[str]):
    return _embed_strings([CFG["prefixes"]["document"] + t for t in texts])


def embed_query(text: str):
    return _embed_strings([CFG["prefixes"]["query"] + text])[0]


# A question asked before does not need the model again: its vector is kept (by a hash of the question,
# never its words) in .index/query_cache.db. A hit answers in a fraction of a second and loads nothing.
QUERY_CACHE = INDEX_DIR / "query_cache.db"
QUERY_CACHE_MAX = 2000


def _query_key(text: str) -> str:
    return hashlib.sha256((MODEL_ID + "\x1f" + CFG["prefixes"]["query"] + " ".join(text.split())).encode("utf-8")).hexdigest()


def embed_query_cached(text: str):
    """The question's vector, from the cache when it was asked before. BRAIN_EMBED_NO_CACHE=1 turns it off."""
    import numpy as np
    if os.environ.get("BRAIN_EMBED_NO_CACHE") == "1":
        return embed_query(text)
    key = _query_key(text)
    con = None
    try:
        con = sqlite3.connect(str(QUERY_CACHE), timeout=5)
        con.execute("CREATE TABLE IF NOT EXISTS qv (key TEXT PRIMARY KEY, vec BLOB NOT NULL, used REAL NOT NULL)")
        row = con.execute("SELECT vec FROM qv WHERE key = ?", (key,)).fetchone()
        if row and len(row[0]) == DIM * 4:
            con.execute("UPDATE qv SET used = ? WHERE key = ?", (time.time(), key))
            con.commit()
            return np.frombuffer(row[0], dtype="<f4").astype(np.float32)
    except sqlite3.Error:
        con = None                       # the cache is a convenience: without it the model answers
    vec = embed_query(text)
    if con is not None:
        try:
            con.execute("INSERT OR REPLACE INTO qv (key, vec, used) VALUES (?,?,?)",
                        (key, np.asarray(vec, dtype="<f4").tobytes(), time.time()))
            con.execute("DELETE FROM qv WHERE key NOT IN (SELECT key FROM qv ORDER BY used DESC LIMIT ?)",
                        (QUERY_CACHE_MAX,))
            con.commit()
        except sqlite3.Error:
            pass
    return vec


def pack(vec) -> tuple[bytes, bytes]:
    """(bin, full) blobs for one unit vector."""
    import numpy as np
    bits = np.packbits(vec > 0, bitorder="big").tobytes()  # dim 0 = MSB of byte 0
    if CFG["storage"]["full_format"] == "int8":
        scale = float(np.max(np.abs(vec))) or 1.0
        q = np.clip(np.round(vec / scale * 127), -127, 127).astype("<i1")
        full = np.array([scale], dtype="<f4").tobytes() + q.tobytes()  # 4-byte scale, then 768 int8
    else:
        full = vec.astype("<f2").tobytes()
    return bits, full


def unpack_full(blob: bytes):
    import numpy as np
    if CFG["storage"]["full_format"] == "int8":
        scale = float(np.frombuffer(blob[:4], dtype="<f4")[0])
        return np.frombuffer(blob[4:], dtype="<i1").astype(np.float32) * (scale / 127.0)
    return np.frombuffer(blob, dtype="<f2").astype(np.float32)


# ----------------------------------------------------------------- pending

def _acquire_lock():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        raise RuntimeError("another embed run holds .index/embed.lock")
    return fh


def _pending_impl(index_db_path: str, limit: int | None = None, dry_run: bool = False) -> dict:
    index_db = Path(index_db_path)
    spec = _graph_spec()
    rows = _catalogue_rows(index_db)
    vdb = _open_vectors()
    old_map = {
        r[0]: r for r in vdb.execute(
            "SELECT path, sha256, src_path, src_size, src_mtime FROM file_map")
    }
    have_keys = {r[0] for r in vdb.execute("SELECT DISTINCT sha256 FROM vectors")}

    counts: Counter = Counter()
    new_map: list[tuple] = []
    pending: dict[str, tuple[str, str]] = {}  # key -> (text, first path)
    t0 = time.time()
    for rel, file_sha in rows:
        reason = exclusion_reason(rel, spec)
        if reason:
            counts["excluded:" + reason] += 1
            continue
        src = _text_source(rel)
        if src is None:
            counts["no_text"] += 1
            continue
        try:
            st = src.stat()
        except OSError:
            counts["missing_on_disk"] += 1
            continue
        old = old_map.get(rel)
        text = None
        if old and old[2] == str(src) and old[3] == st.st_size and old[4] == int(st.st_mtime):
            key = old[1]  # unchanged source: reuse the content key without reading
        else:
            text = _read_source_text(src)
            if not text:
                counts["no_text"] += 1
                continue
            key = content_key(text)
        new_map.append((rel, key, file_sha, str(src), st.st_size, int(st.st_mtime)))
        if key in have_keys or key in pending:
            continue
        if text is None:
            text = _read_source_text(src)
            if not text:
                counts["no_text"] += 1
                continue
        pending[key] = (text, rel)
    counts["eligible"] = len(new_map)
    log(f"scan: {len(rows)} catalogue rows, {len(new_map)} eligible, "
        f"{len(pending)} new texts to embed ({time.time() - t0:.1f}s)")

    if dry_run:
        n_chunks = sum(len(chunk_text(redact(t)[0])) for t, _ in pending.values())
        return {"dry_run": True, "new_texts": len(pending), "new_chunks": n_chunks,
                "counts": dict(counts)}

    lock = _acquire_lock()
    started = utc_now()
    t_start = time.time()
    if limit is not None:
        pending = dict(list(sorted(pending.items(), key=lambda kv: kv[1][1]))[:limit])

    # file_map is a view of the catalogue: rebuilt every run, keys are content.
    with vdb:
        vdb.execute("DELETE FROM file_map")
        vdb.executemany(
            "INSERT INTO file_map (path, sha256, file_sha256, src_path, src_size, src_mtime) "
            "VALUES (?, ?, ?, ?, ?, ?)", new_map)

    chunks_new = 0
    keys_done = 0
    errors = 0
    total_keys = len(pending)
    redactions = 0
    for key, (text, rel) in sorted(pending.items(), key=lambda kv: kv[1][1]):
        text, k = redact(text)  # stored and embedded text is the redacted text only
        redactions += k
        chunks = chunk_text(text)
        if not chunks:
            continue
        try:
            vecs = embed_documents(chunks)
        except Exception as exc:  # one bad text must not stop the run
            errors += 1
            log(f"ERROR embedding {rel}: {exc}")
            continue
        c_rows = [(key, i, c, len(c)) for i, c in enumerate(chunks)]
        v_rows = []
        for i, v in enumerate(vecs):
            b, f = pack(v)
            v_rows.append((key, i, b, f, MODEL_ID))
        with vdb:  # one transaction per content key: a key is either complete or absent
            vdb.executemany("INSERT OR REPLACE INTO chunks VALUES (?, ?, ?, ?)", c_rows)
            vdb.executemany("INSERT OR REPLACE INTO vectors VALUES (?, ?, ?, ?, ?)", v_rows)
        chunks_new += len(chunks)
        keys_done += 1
        if keys_done % 25 == 0 or keys_done == total_keys:
            rate = chunks_new / max(time.time() - t_start, 1e-9)
            log(f"embedded {keys_done}/{total_keys} texts, {chunks_new} chunks, {rate:.1f} chunks/s")

    total = vdb.execute("SELECT count(*) FROM vectors").fetchone()[0]
    seconds = time.time() - t_start
    excluded = {k: v for k, v in counts.items() if k.startswith("excluded:")}
    with vdb:
        vdb.execute(
            "INSERT INTO embed_runs (started_at, finished_at, model, index_db, catalogue_files, "
            "eligible_files, keys_new, chunks_new, chunks_total, seconds, excluded_json, no_text, "
            "errors, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (started, utc_now(), MODEL_ID, str(index_db), len(rows), len(new_map), keys_done,
             chunks_new, total, round(seconds, 2), json.dumps(excluded, sort_keys=True),
             counts.get("no_text", 0), errors, "limit=%s" % limit if limit else None))
    vdb.close()
    lock.close()
    log(f"done: {keys_done} texts, {chunks_new} chunks in {seconds:.1f}s, errors={errors}")
    log(f"redactions applied: {redactions}")
    return {"chunks": chunks_new, "keys": keys_done, "errors": errors, "redactions": redactions,
            "counts": dict(counts), "seconds": round(seconds, 2)}


def embed_pending(index_db_path=DEFAULT_INDEX_DB, limit: int | None = None,
                  dry_run: bool = False) -> int:
    """Chunk and embed every catalogue file whose text has no vectors yet.

    Returns the number of chunks embedded in this run (0 on a dry run).
    """
    if not _heavy_ready():
        res = _relaunch("embed_pending", {"index_db_path": str(index_db_path),
                                          "limit": limit, "dry_run": dry_run})
    else:
        res = _pending_impl(str(index_db_path), limit=limit, dry_run=dry_run)
    return int(res.get("chunks", 0))


# ----------------------------------------------------------------- search

_POP = None


def _popcount_table():
    import numpy as np
    global _POP
    if _POP is None:
        _POP = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint16)
    return _POP


def _search_impl(index_db_path: str, query: str, k: int = 20, exact: bool = False,
                 shortlist: int = 300) -> list[dict]:
    import numpy as np
    qv = embed_query_cached(query)
    vdb = _open_vectors()
    n = vdb.execute("SELECT count(*) FROM vectors").fetchone()[0]
    if n == 0:
        vdb.close()
        return []
    keys, ords, bins, fulls = [], [], [], []
    for sha, o, b, f in vdb.execute("SELECT sha256, ord, bin, full FROM vectors"):
        keys.append(sha); ords.append(o); bins.append(b); fulls.append(f)
    if exact:
        # every chunk scored with its full vector
        mat = np.stack([unpack_full(f) for f in fulls])
        scores = mat @ qv
        order = np.argsort(-scores)
        cand, scores = order, scores[order]
        hamming = None
    else:
        # 1) Hamming distance on the sign bits, 2) exact cosine on the best `shortlist`
        bmat = np.frombuffer(b"".join(bins), dtype=np.uint8).reshape(n, BIN_BYTES)
        qbits = np.packbits(qv > 0)
        hamming = _popcount_table()[bmat ^ qbits].sum(axis=1)
        m = min(shortlist, n)
        pool = np.argpartition(hamming, m - 1)[:m] if m < n else np.arange(n)
        mat = np.stack([unpack_full(fulls[i]) for i in pool])
        s = mat @ qv
        order = np.argsort(-s)
        cand, scores = pool[order], s[order]

    fmap: dict[str, list[str]] = {}
    for path, sha in vdb.execute("SELECT path, sha256 FROM file_map"):
        fmap.setdefault(sha, []).append(path)

    hits: list[dict] = []
    seen_paths: set[str] = set()
    for rank_i, idx in enumerate(cand):
        sha, o = keys[idx], ords[idx]
        for path in sorted(fmap.get(sha, [])):
            if path in seen_paths:
                continue
            seen_paths.add(path)
            text = vdb.execute("SELECT text FROM chunks WHERE sha256=? AND ord=?", (sha, o)).fetchone()
            hits.append({
                "path": path,
                "sha256": sha,
                "ord": int(o),
                "score": round(float(scores[rank_i]), 5),
                "hamming": int(hamming[idx]) if hamming is not None else None,
                "text": text[0] if text else "",
            })
            if len(hits) >= k:
                break
        if len(hits) >= k:
            break
    vdb.close()
    return hits


def search(index_db_path=DEFAULT_INDEX_DB, query: str = "", k: int = 20,
           exact: bool = False) -> list[dict]:
    """One hit per document, best chunk first. Bit search over all vectors, then re-score
    the best 300 with the full vectors. exact=True scores every chunk with the full vectors."""
    if not _heavy_ready():
        return _relaunch("search", {"index_db_path": str(index_db_path), "query": query,
                                    "k": k, "exact": exact})
    return _search_impl(str(index_db_path), query, k=k, exact=exact)


# ----------------------------------------------------------------- stats / selftest

def _stats() -> dict:
    vdb = _open_vectors()
    out = {
        "vectors_db": str(VECTORS_DB),
        "db_bytes": VECTORS_DB.stat().st_size if VECTORS_DB.exists() else 0,
        "chunks": vdb.execute("SELECT count(*) FROM chunks").fetchone()[0],
        "vectors": vdb.execute("SELECT count(*) FROM vectors").fetchone()[0],
        "content_keys": vdb.execute("SELECT count(DISTINCT sha256) FROM vectors").fetchone()[0],
        "file_map_rows": vdb.execute("SELECT count(*) FROM file_map").fetchone()[0],
        "model": MODEL_ID,
    }
    last = vdb.execute("SELECT id, started_at, finished_at, eligible_files, keys_new, chunks_new, "
                       "chunks_total, seconds, excluded_json, no_text, errors FROM embed_runs "
                       "ORDER BY id DESC LIMIT 1").fetchone()
    if last:
        cols = ["id", "started_at", "finished_at", "eligible_files", "keys_new", "chunks_new",
                "chunks_total", "seconds", "excluded_json", "no_text", "errors"]
        out["last_run"] = dict(zip(cols, last))
    vdb.close()
    return out


def _selftest() -> dict:
    import numpy as np
    pairs = [
        "task: search result | query: Which planet is known as the Red Planet?",
        "title: none | text: Mars is known as the Red Planet.",
        "title: none | text: Venus is often called Earth's twin.",
    ]
    vecs = _embed_strings(pairs)
    sims = vecs[0] @ vecs[1:].T
    return {"ok": bool(vecs.shape == (3, DIM) and np.all(np.isfinite(vecs))
                       and sims[0] > sims[1]),
            "shape": list(vecs.shape),
            "norms": [round(float(x), 5) for x in np.linalg.norm(vecs, axis=1)],
            "cos_query_mars": round(float(sims[0]), 4),
            "cos_query_venus": round(float(sims[1]), 4),
            "mars_above_venus": bool(sims[0] > sims[1]),
            "model": MODEL_ID}


# ----------------------------------------------------------------- CLI

def _cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("pending")
    p1.add_argument("--index-db", default=str(DEFAULT_INDEX_DB))
    p1.add_argument("--limit", type=int)
    p1.add_argument("--dry-run", action="store_true")
    p2 = sub.add_parser("search")
    p2.add_argument("query")
    p2.add_argument("-k", type=int, default=20)
    p2.add_argument("--exact", action="store_true")
    p2.add_argument("--json", action="store_true")
    p2.add_argument("--index-db", default=str(DEFAULT_INDEX_DB))
    sub.add_parser("stats")
    sub.add_parser("selftest")
    p5 = sub.add_parser("_call")
    p5.add_argument("op")
    p5.add_argument("payload")
    a = ap.parse_args(argv)

    if a.cmd == "pending":
        if a.dry_run:
            res = _pending_impl(a.index_db, limit=a.limit, dry_run=True)
        else:
            res = _pending_impl(a.index_db, limit=a.limit)
        print(json.dumps(res, indent=2, ensure_ascii=False))
    elif a.cmd == "search":
        hits = _search_impl(a.index_db, a.query, k=a.k, exact=a.exact)
        if a.json:
            print(json.dumps(hits, ensure_ascii=False, indent=2))
        else:
            for i, h in enumerate(hits, 1):
                snippet = re.sub(r"\s+", " ", h["text"])[:160]
                print(f"{i:2d}. {h['score']:.4f}  {h['path']}\n      {snippet}")
    elif a.cmd == "stats":
        print(json.dumps(_stats(), indent=2, ensure_ascii=False, default=str))
    elif a.cmd == "selftest":
        res = _selftest()
        print(json.dumps(res, indent=2))
        return 0 if res["ok"] else 1
    elif a.cmd == "_call":
        payload = json.loads(a.payload)
        try:
            if a.op == "embed_pending":
                result = _pending_impl(payload["index_db_path"], limit=payload.get("limit"),
                                       dry_run=bool(payload.get("dry_run")))
            elif a.op == "search":
                result = _search_impl(payload["index_db_path"], payload["query"],
                                      k=int(payload.get("k", 20)), exact=bool(payload.get("exact")))
            else:
                raise RuntimeError(f"unknown op {a.op}")
            print(RESULT_TAG + json.dumps({"ok": True, "result": result}, ensure_ascii=False))
        except Exception as exc:
            print(RESULT_TAG + json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
            return 1
    return 0


if __name__ == "__main__":
    # Heavy commands started with a plain python3 hand over to the private environment.
    if len(sys.argv) >= 2 and sys.argv[1] in ("pending", "search", "selftest") \
            and not _heavy_ready() and os.environ.get(CHILD_ENV) != "1":
        if not VENV_PY.exists():
            sys.exit("venv missing: run tools/index/embed/setup.sh")
        os.environ[CHILD_ENV] = "1"
        os.execv(str(VENV_PY), [str(VENV_PY), str(Path(__file__).resolve())] + sys.argv[1:])
    sys.exit(_cli(sys.argv[1:]))
