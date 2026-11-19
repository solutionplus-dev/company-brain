#!/usr/bin/env python3
"""Library half of tools/index/supabase_sync.py: scope rules, local sources, row builders.

No network here. Standard library only. Nothing in this module prints row content.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import brain_redact

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import brainconfig  # noqa: E402

ENTITY_CODES = brainconfig.codes()

NS = uuid.UUID("9f31ddd5-41e5-41dd-8603-70f0511f7a1b")  # fixed: ids must stay stable across runs
SCOPE_RE = re.compile(r"^(finance|ops|gtm|outreach|templates|design|client:[a-z0-9][a-z0-9_-]{0,62})$")
MODULE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
DOC_DATE = re.compile(r"^[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
DIM = 768


class ConfigError(Exception):
    pass


class LocalError(Exception):
    pass


def uid(*parts) -> str:
    return str(uuid.uuid5(NS, json.dumps(parts, ensure_ascii=False, separators=(",", ":"))))


def slugify(raw: str) -> str | None:
    if not raw or raw[0] in "._" or raw.startswith(" "):
        return None
    s = re.sub(r"[ .]+", "-", raw.lower())
    s = re.sub(r"[^a-z0-9_-]", "", s)[:63]
    return s if s and s[0].isalnum() else None


# ----------------------------------------------------------------- scope rules

class ScopeConfig:
    def __init__(self, data: dict, origin: str = "scopes.json"):
        try:
            self.flag = data["owner_confirmed_private_scopes"] is True
            self.private = list(data["private_scopes"])
            self.client_allowed = {str(s).lower() for s in data.get("client_scopes_allowed", [])}
            nv = data["never"]
            self.never_prefixes = []
            for e in nv.get("path_prefixes", []):
                if isinstance(e, str):
                    self.never_prefixes.append((e.lower(), ()))
                else:
                    self.never_prefixes.append((e["prefix"].lower(), tuple(x.lower() for x in e.get("unless_ext", []))))
            self.never_contains = [s.lower() for s in nv.get("path_contains", [])]
            self.never_segments = {s.lower() for s in nv.get("path_segments", [])}
            self.never_names = [s.lower() for s in nv.get("name_patterns", [])]
            self.never_prefix_names = [(e["prefix"].lower(), [t.lower() for t in e["name_contains"]])
                                       for e in nv.get("prefix_name_patterns", [])]
            self.never_terms = [t.lower() for t in data.get("never_text_terms", [])]
            content = data.get("content", {})
            self.chunk_exts = {e.lower() for e in content.get("chunk_text_extensions", [".md", ".txt"])}
            self.renditions = [p.lower() for p in content.get("rendition_patterns", [])]
            self.rules = [self._compile_rule(r) for r in data["rules"]]
            self.area_rules = {r["area"]: (r["scope"], r.get("module", "core")) for r in data.get("area_rules", [])}
            self.kind_scopes = {k: v for k, v in data.get("record_kind_scopes", {}).items() if not k.startswith("_")}
        except (KeyError, TypeError) as exc:
            raise ConfigError(f"{origin}: missing or malformed field {exc}") from None
        for s in self.kind_scopes.values():
            if not SCOPE_RE.match(s):
                raise ConfigError(f"{origin}: record_kind_scopes holds an invalid scope")

    @classmethod
    def load(cls, path) -> "ScopeConfig":
        try:
            return cls(json.loads(Path(path).read_text(encoding="utf-8")), str(path))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"cannot read {path}: {exc.__class__.__name__}") from None

    @staticmethod
    def _compile_rule(r: dict):
        prefix, scope, module = r["prefix"], r.get("scope"), r.get("module", "core")
        if scope is not None:
            probe = scope.replace("{slug}", "x")
            if not SCOPE_RE.match(probe) or not MODULE_RE.match(module):
                raise ConfigError(f"rule {prefix!r}: invalid scope or module")
        if "{slug}" in prefix:
            a, b = prefix.split("{slug}", 1)
            return ("re", re.compile("^" + re.escape(a) + r"([^/]+)" + re.escape(b)), scope, module)
        return ("prefix", prefix, scope, module)

    # -- never list
    def never_reason(self, path: str) -> str | None:
        low = path.lower()
        parts = low.split("/")
        name, ext = parts[-1], os.path.splitext(parts[-1])[1]
        for pre, unless in self.never_prefixes:
            if low.startswith(pre) and ext not in unless:
                return "prefix"
        for s in self.never_contains:
            if s in low:
                return "contains"
        if any(seg in self.never_segments for seg in parts[:-1]):
            return "segment"
        for pat in self.never_names:
            if fnmatch.fnmatchcase(name, pat):
                return "name"
        for pre, terms in self.never_prefix_names:
            if low.startswith(pre) and any(t in low[len(pre):] for t in terms):
                return "client-pattern"
        return None

    def has_never_term(self, text: str | None) -> bool:
        if not text or not self.never_terms:
            return False
        low = text.lower()
        return any(t in low for t in self.never_terms)

    # -- routing
    def rule_scope(self, path: str, area: str | None = None):
        """(scope or None, module, reason), never list NOT applied."""
        for kind, pat, scope, module in self.rules:
            if kind == "prefix":
                if not path.startswith(pat):
                    continue
                return (scope, module, "rule") if scope else (None, None, "local-rule")
            m = pat.match(path)
            if not m:
                continue
            slug = slugify(m.group(1))
            if slug is None:
                continue
            if scope is None:
                return None, None, "local-rule"
            return scope.replace("{slug}", slug), module, "rule"
        if area and area.startswith("finance-") and area not in self.area_rules:
            area = "finance"  # every legal entity's finance area shares the finance rule
        if area and area in self.area_rules:
            scope, module = self.area_rules[area]
            return (scope, module, "area") if scope else (None, None, "local-rule")
        return None, None, "unmapped"

    def route(self, path: str, area: str | None = None):
        """('never'|'local'|'scope', scope, module, reason). For 'never', scope is the would-be scope."""
        scope, module, reason = self.rule_scope(path, area)
        nr = self.never_reason(path)
        if nr:
            return "never", scope, None, nr
        if scope is None:
            return "local", None, None, reason
        return "scope", scope, module, reason

    def is_private(self, scope: str) -> bool:
        return any(fnmatch.fnmatchcase(scope, p) for p in self.private)

    def scope_allowed(self, scope: str) -> tuple[bool, str]:
        if not SCOPE_RE.match(scope or ""):
            return False, "not a valid scope name"
        if self.is_private(scope) and not self.flag:
            return False, "private scope; owner_confirmed_private_scopes is false"
        if scope.startswith("client:") and scope[7:] not in self.client_allowed:
            return False, "client not listed in client_scopes_allowed"
        return True, "allowed"

    def chunkable(self, path: str) -> bool:
        low = path.lower()
        name = low.rsplit("/", 1)[-1]
        if any(fnmatch.fnmatchcase(name, p) for p in self.renditions):
            return False
        return low.endswith(".digest.md") or os.path.splitext(name)[1] in self.chunk_exts


# ----------------------------------------------------------------- vectors

def bits_from_blob(blob: bytes) -> str:
    if len(blob) != DIM // 8:
        raise ValueError("bin blob has the wrong length")
    return "".join(f"{b:08b}" for b in blob)  # numpy packbits order: character i = dimension i


def floats_from_full(blob: bytes) -> list[float]:
    import struct
    if len(blob) == 4 + DIM:  # float32 scale + int8 values
        scale = struct.unpack("<f", blob[:4])[0]
        return [q * scale / 127.0 for q in struct.unpack(f"<{DIM}b", blob[4:])]
    if len(blob) == 2 * DIM:
        return list(struct.unpack(f"<{DIM}e", blob))
    if len(blob) == 4 * DIM:
        return list(struct.unpack(f"<{DIM}f", blob))
    raise ValueError("full blob has an unknown layout")


def halfvec_text(vals: list[float]) -> str:
    if len(vals) != DIM or not all(math.isfinite(v) for v in vals):
        raise ValueError("vector is not 768 finite values")
    return "[" + ",".join(f"{v:.5g}" for v in vals) + "]"


def chunk_text(text: str, size: int = 1200, overlap: int = 150) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        while len(p) > size:
            cut = p.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            pieces = p[:cut]
            if cur:
                out.append(cur)
                cur = ""
            out.append(pieces)
            p = p[max(cut - overlap, 1):].lstrip()
        cand = (cur + "\n\n" + p) if cur else p
        if len(cand) <= size:
            cur = cand
        else:
            out.append(cur)
            cur = (cur[-overlap:] + "\n\n" + p) if overlap and cur else p
    if cur:
        out.append(cur)
    return out


def _ro(path: Path) -> sqlite3.Connection:
    if not Path(path).exists():
        raise LocalError(f"missing local database: {path}")
    con = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def _iso(ts) -> str | None:
    try:
        return datetime.fromtimestamp(float(ts), timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


# ----------------------------------------------------------------- local sources

class IndexSource:
    """The vault's own index: .index/vault_index.db (+ .index/vectors.db when present)."""

    def __init__(self, index_db, vectors_db=None, root=None, source="vault"):
        self.idx = _ro(index_db)
        self.source = source
        self.root = str(Path(root).resolve()) + "/" if root else str(Path(index_db).resolve().parents[1]) + "/"
        cols = {r[1] for r in self.idx.execute("pragma table_info(files)")}
        want = ["path", "name", "ext", "size", "mtime", "sha256", "entity", "area", "tier", "doc_date", "has_digest"]
        sel = ", ".join(c if c in cols else f"NULL AS {c}" for c in want)
        self._files = [dict(r) for r in self.idx.execute(f"select {sel} from files order by path")]
        self.vec = _ro(vectors_db) if vectors_db and Path(vectors_db).exists() else None
        self.fmap, self.counts = {}, {}
        if self.vec is not None:
            for r in self.vec.execute("select path, sha256, src_path from file_map"):
                src = r["src_path"] or ""
                if src.startswith(self.root):
                    src = src[len(self.root):]
                self.fmap[r["path"]] = (r["sha256"], src)
            q = ("select c.sha256 s, count(*) n, count(v.ord) nv, max(v.model) m from chunks c "
                 "left join vectors v on v.sha256 = c.sha256 and v.ord = c.ord group by c.sha256")
            for r in self.vec.execute(q):
                self.counts[r["s"]] = (r["n"], r["nv"], r["m"] or "")

    @property
    def has_vectors(self) -> bool:
        return self.vec is not None

    def files(self) -> list[dict]:
        return self._files

    def content_key(self, cfg: ScopeConfig, path: str) -> str | None:
        if self.vec is not None:
            ent = self.fmap.get(path)
            if not ent:
                return None
            sha, src = ent
            if cfg.chunkable(path):
                return sha
            # a binary travels only through its digest, and only when the digest has no row of its own
            if src.lower().endswith(".digest.md") and src not in self.fmap and cfg.never_reason(src) is None:
                return sha
            return None
        if not cfg.chunkable(path):
            return None
        text = self._fts_text(path)
        return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None

    def _fts_text(self, path: str) -> str | None:
        try:
            row = self.idx.execute("select digest_text from files_fts where path = ?", (path,)).fetchone()
        except sqlite3.Error:
            return None
        return row[0] if row and row[0] else None

    def counts_for(self, key: str):
        return self.counts.get(key)

    def load_chunks(self, path: str, key: str) -> list[tuple]:
        if self.vec is not None:
            q = ("select c.ord, c.text, v.bin, v.full, v.model from chunks c left join vectors v "
                 "on v.sha256 = c.sha256 and v.ord = c.ord where c.sha256 = ? order by c.ord")
            return [tuple(r) for r in self.vec.execute(q, (key,))]
        text = self._fts_text(path) or ""
        return [(i, t, None, None, None) for i, t in enumerate(chunk_text(text))]

    def records(self) -> list[dict]:
        try:
            return [dict(r) for r in self.idx.execute("select * from records order by id")]
        except sqlite3.Error:
            return []

    def edges(self) -> list[tuple]:
        try:
            return [tuple(r) for r in self.idx.execute("select src, dst, rel from edges")]
        except sqlite3.Error:
            return []


class WalkSource:
    """Another brain on disk (a repository folder): text files only, no records, no vectors."""
    SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".cache"}
    MAX_TEXT = 2_000_000

    def __init__(self, directory, prefix: str, source: str):
        self.dir = Path(directory).resolve()
        if not self.dir.is_dir():
            raise LocalError(f"not a folder: {directory}")
        self.source, self._files, self._abs = source, [], {}
        self.fenced = 0
        fence_dirs, fence_pats = self._read_fence()
        for base, dirs, names in os.walk(self.dir, followlinks=False):
            kept = []
            for d in sorted(dirs):
                if d in self.SKIP_DIRS or d.startswith("."):
                    continue
                if d.lower() in fence_dirs:
                    self.fenced += 1          # a fenced folder: never entered, never listed
                    continue
                kept.append(d)
            dirs[:] = kept
            for n in sorted(names):
                ap = Path(base) / n
                if ap.is_symlink() or not ap.is_file():
                    continue
                relp = ap.relative_to(self.dir).as_posix()
                if any(fnmatch.fnmatch(relp.lower(), pat) or fnmatch.fnmatch(n.lower(), pat) for pat in fence_pats):
                    self.fenced += 1          # a fenced file: never opened, never uploaded
                    continue
                rel = prefix + relp
                st = ap.stat()
                self._abs[rel] = ap
                self._files.append({"path": rel, "name": n, "ext": ap.suffix.lower(), "size": st.st_size,
                                    "mtime": st.st_mtime, "sha256": None, "entity": None, "area": None,
                                    "tier": None, "doc_date": None, "has_digest": 0})

    has_vectors = False

    # The never-read list of a walked brain. Built-in defaults plus the brain's own
    # `.brainignore` at its root: one pattern per line, `#` starts a comment, a trailing `/` names a
    # folder that is fenced wherever it appears, anything else is an fnmatch pattern on the path
    # relative to the brain's root (or on the bare file name). A fenced file or folder is skipped
    # before anything is read: it can only narrow what leaves this computer, never widen it.
    FENCE_DIRS = {"exports", "dumps", "raw-data", ".secrets", "secrets"}
    FENCE_PATTERNS = [".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks", "*.sql", "*.dump"]

    def _read_fence(self):
        dirs = set(self.FENCE_DIRS)
        pats = [p.lower() for p in self.FENCE_PATTERNS]
        f = self.dir / ".brainignore"
        if f.is_file():
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.split("#", 1)[0].strip()
                if not line:
                    continue
                if line.endswith("/"):
                    dirs.add(line.rstrip("/").split("/")[-1].lower())
                else:
                    pats.append(line.lower())
        return dirs, pats

    def files(self):
        return self._files

    def _text(self, path):
        ap = self._abs.get(path)
        if not ap or ap.stat().st_size > self.MAX_TEXT:
            return None
        return ap.read_bytes().decode("utf-8", errors="replace")

    def content_key(self, cfg, path):
        if not cfg.chunkable(path):
            return None
        t = self._text(path)
        return hashlib.sha256(t.encode("utf-8")).hexdigest() if t else None

    def counts_for(self, key):
        return None

    def load_chunks(self, path, key):
        return [(i, t, None, None, None) for i, t in enumerate(chunk_text(self._text(path) or ""))]

    def records(self):
        return []

    def edges(self):
        return []


# ----------------------------------------------------------------- row builders

def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _redact_obj(o, cnt: list):
    if isinstance(o, str):
        t, n = brain_redact.redact(o)
        cnt[0] += n
        return t
    if isinstance(o, list):
        return [_redact_obj(x, cnt) for x in o]
    if isinstance(o, dict):
        return {k: _redact_obj(v, cnt) for k, v in o.items()}
    return o


class Builder:
    def __init__(self, cfg: ScopeConfig, src, scope_override: str | None = None,
                 module_override: str | None = None):
        self.cfg, self.src = cfg, src
        self.scope_override, self.module_override = scope_override, module_override
        self.blocked, self.local = {}, {"local-rule": 0, "unmapped": 0}
        self.docs = {}  # scope -> list of dict(row=..., key=...)
        for f in src.files():
            path = f["path"]
            status, scope, module, reason = cfg.route(path, f.get("area"))
            if status != "never" and scope_override:
                status, scope, module = "scope", scope_override, module_override or "core"
            if status == "never":
                self.blocked[scope or "(none)"] = self.blocked.get(scope or "(none)", 0) + 1
                continue
            if status == "local":
                self.local[reason] = self.local.get(reason, 0) + 1
                continue
            self.docs.setdefault(scope, []).append({"row": self._doc_row(f, scope, module),
                                                    "key": src.content_key(cfg, path)})

    def _doc_row(self, f, scope, module) -> dict:
        title, _ = brain_redact.redact(f.get("name") or f["path"].rsplit("/", 1)[-1])
        sha = (f.get("sha256") or "").lower()
        dd = f.get("doc_date")
        ent = (f.get("entity") or "").upper()
        size = f.get("size")
        return {"id": uid("doc", scope, f["path"]), "scope": scope, "module": module,
                "source": self.src.source, "path": f["path"], "sha256": sha if HEX64.match(sha) else None,
                "text_key": None, "redaction": brain_redact.REDACTION_ID, "title": title,
                "area": f.get("area"), "tier": f.get("tier"),
                "company": ent if ent in ENTITY_CODES else None,
                "doc_date": dd if isinstance(dd, str) and DOC_DATE.match(dd) else None,
                "has_digest": bool(f.get("has_digest")),
                "size": int(size) if isinstance(size, (int, float)) and size >= 0 else None,
                "n_chunks": 0, "updated_at": _iso(f.get("mtime"))}

    def fingerprint(self, doc) -> str | None:
        key = doc["key"]
        if not key:
            return None
        counts = self.src.counts_for(key)
        raw = "|".join([key, brain_redact.REDACTION_ID, ",".join(self.cfg.never_terms), json.dumps(counts)])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def chunk_rows(self, doc):
        """(chunks, embeddings, stats) for one document; texts redacted, never-term chunks dropped."""
        key, row = doc["key"], doc["row"]
        chunks, embs, st = [], [], {"redacted": 0, "dropped": 0}
        if not key:
            return chunks, embs, st
        for ordv, text, b, full, model in self.src.load_chunks(row["path"], key):
            if self.cfg.has_never_term(text):
                st["dropped"] += 1
                continue
            red, n = brain_redact.redact(text or "")
            if n:
                st["redacted"] += 1
            if not red.strip():
                continue
            cid = uid("chunk", row["id"], int(ordv))
            chunks.append({"id": cid, "document_id": row["id"], "scope": row["scope"],
                           "ord": int(ordv), "text": red[:20000]})
            if b is not None and full is not None:
                embs.append({"chunk_id": cid, "scope": row["scope"], "_bin": b, "_full": full,
                             "model": (model or "unknown")[:200]})
        return chunks, embs, st

    @staticmethod
    def embedding_payload(e: dict) -> dict:
        return {"chunk_id": e["chunk_id"], "scope": e["scope"], "bin": bits_from_blob(e["_bin"]),
                "full": halfvec_text(floats_from_full(e["_full"])), "model": e["model"]}

    def record_rows(self):
        out, st = {}, {"blocked": 0, "local": 0, "dropped": 0, "invalid": 0, "redacted": 0, "duplicate": 0}
        seen = set()
        for r in self.src.records():
            kind, sp = r.get("kind"), r.get("source_path") or ""
            status, would, _, _ = self.cfg.route(sp, None)
            if status == "never" or not kind:
                st["blocked"] += 1
                continue
            scope = self.cfg.kind_scopes.get(kind) or (would if status == "scope" else None)
            if scope is None:
                st["local"] += 1
                continue
            try:
                extra = json.loads(r["extra"]) if r.get("extra") else None
            except (TypeError, ValueError):
                extra = {"raw": r.get("extra")}
            fields = ["ref", "title", "amount_text", "counterparty", "status", "client", "certainty"]
            blob = " ".join(str(r.get(k) or "") for k in fields) + " " + json.dumps(extra, ensure_ascii=False)
            if self.cfg.has_never_term(blob) or self.cfg.has_never_term(sp):
                st["dropped"] += 1
                continue
            ex = extra if isinstance(extra, dict) else {}
            company = r.get("company") if r.get("company") in ENTITY_CODES + ("both", "none") else None
            currency = (r.get("currency") or "").strip().upper() or None
            if kind == "ledger_line" and (company not in ENTITY_CODES or not currency or not CURRENCY.match(currency)):
                st["invalid"] += 1
                continue
            cnt = [0]
            row = {"id": uid("rec", scope, kind, r.get("ref"), sp, r.get("source_line")),
                   "scope": scope, "source": self.src.source, "kind": kind, "company": company}
            for k in fields:
                row[k] = _redact_obj(str(r.get(k)), cnt) if r.get(k) is not None else None
            row.update({"date": r.get("date"), "due_date": r.get("due_date"), "amount": _num(r.get("amount")),
                        "currency": currency, "account": _redact_obj(str(r.get("account") or ex.get("account") or ""), cnt) or None,
                        "debit": _num(r.get("debit", ex.get("debit"))), "credit": _num(r.get("credit", ex.get("credit"))),
                        "source_path": sp, "source_line": r.get("source_line"),
                        "extra": _redact_obj(extra, cnt) if extra is not None else None})
            if row["id"] in seen:
                st["duplicate"] += 1
                continue
            seen.add(row["id"])
            st["redacted"] += 1 if cnt[0] else 0
            out.setdefault(scope, []).append(row)
        return out, st

    def edge_rows(self):
        where = {d["row"]["path"]: s for s, ds in self.docs.items() for d in ds}
        out = {}
        for src_, dst, rel in self.src.edges():
            s = where.get(src_)
            if not s or self.cfg.has_never_term(f"{src_} {dst}"):
                continue
            if dst in where:
                if where[dst] != s:
                    continue
            elif not (rel == "in_folder" and src_.startswith(dst.rstrip("/") + "/")
                      and self.cfg.never_reason(dst.rstrip("/") + "/x.md") is None):
                continue
            out.setdefault(s, []).append({"id": uid("edge", s, src_, dst, rel), "scope": s,
                                          "source": self.src.source, "src": src_, "dst": dst, "rel": rel})
        return out
