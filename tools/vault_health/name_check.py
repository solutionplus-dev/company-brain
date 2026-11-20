#!/usr/bin/env python3
"""List files whose name explains nothing, with a better name and how certain it is. Proposes only.

  python3 tools/vault_health/name_check.py            write 00_Brain/SYSTEM/NAME_SUGGESTIONS.md and print the counts
  python3 tools/vault_health/name_check.py --print    print the table instead of writing the file
  python3 tools/vault_health/name_check.py --min 0.9  only suggestions at least this certain

Rule: AGENTS.md, "A name must explain the file". A name must explain the file; a raw original is
renamed in the vault without asking only when the better name is at least 90 % certain. This script reads
the index (.index/vault_index.db), never the documents; its certainty is a mechanical estimate from what the
index knows (document date, a digest, a descriptive purpose line, a document kind) and never goes above
80 %: only someone who has read the document can be 90 % certain, and that reader renames. Nothing is
renamed here. Standard library only.
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(os.environ.get("BRAIN_ROOT") or Path(__file__).resolve().parents[2]).resolve()
DB = ROOT / ".index" / "vault_index.db"
OUT = ROOT / "00_Brain" / "SYSTEM" / "NAME_SUGGESTIONS.md"
SKIP_PARTS = ("_Mirror/", "_archive/", "/ARCHIVE/", "tools/", "Repos/", ".claude/", ".cursor/", "02_Meetings/",
              "node_modules/", "/attachments/", "/images/", "examples/", "docs/", "scripts/", "tests/")
ORIGINAL_KINDS = {"document", "expense", "invoice", "email-attachment", "image", "spreadsheet", "media"}
GENERIC = ("scan|img|image|photo|picture|document|doc|file|untitled|unbenannt|download|invoice|rechnung|receipt|"
           "beleg|quittung|offer|angebot|contract|vertrag|attachment|anhang|screenshot|bildschirmfoto|new|neu|copy|"
           "kopie|final|export|report|statement|kontoauszug|letter|brief|form|formular|pdf|page|seite|output|result")
BAD = [
    ("generic word only", re.compile(rf"^(?:{GENERIC})(?:[ _\-]*(?:{GENERIC}))*[ _\-]*\(?\d{{0,6}}\)?$")),
    ("camera or scanner number", re.compile(r"^(?:img|dsc|pxl|scan|doc|mvimg|photo|whatsapp image|screenshot|bildschirmfoto)[ _\-]?[\d ._\-]+(?:at [\d.]+)?$")),
    ("only a number or an id", re.compile(r"^[\d ._\-]{5,}$|^[0-9a-f]{8}-[0-9a-f]{4}-|^[0-9a-f]{16,}$")),
    ("browser copy suffix", re.compile(r".*\(\d\)$|.*[ _\-]copy(?:[ _\-]?\d)?$|.*[ _\-]kopie$")),
]
KINDS = ("invoice", "rechnung", "receipt", "beleg", "quittung", "contract", "vertrag", "agreement", "letter", "brief",
         "bescheid", "statement", "kontoauszug", "certificate", "bescheinigung", "urkunde", "offer", "angebot",
         "proposal", "report", "minutes", "protokoll", "nda", "deed", "licence", "license", "lizenz", "notice",
         "mitteilung", "application", "antrag", "order", "bestellung", "policy", "police", "presentation", "deck")


FIXED = {"readme", "index", "notes", "transcript", "summary", "manifest", "status", "client", "timeline", "todo",
         "registry", "config", "package", "license", "licence", "changelog", "agents", "claude", "brain", "skill",
         "module", "journal", "ledger", "money", "month", "year", "now", "seed", "main", "styles", "tokens",
         "daily", "weekly"}


def poor(stem: str) -> str | None:
    """Why a name explains nothing, or None. Names fixed by convention (registers in capitals, dated logs,
    the standard files of a folder) explain themselves through the convention and are left alone."""
    if re.fullmatch(r"[A-Z][A-Z0-9]*(?:[_-][A-Z0-9a-z-]+)*", stem) or stem.lower() in FIXED:
        return None
    if re.fullmatch(r"\d{4}-(?:\d{2}(?:-\d{2})?|W\d{2})(?:[_ .-][a-z-]{2,12})?", stem) or stem.startswith("_"):
        return None
    s = stem.lower().strip()
    for label, rx in BAD:
        if rx.match(s):
            return label
    words = [w for w in re.findall(r"[^\W\d_]{3,}", s)]
    if len(words) < 2 and not re.search(r"\d{4}-\d{2}-\d{2}", s):
        return "fewer than two words"
    return None


def slug(text: str, words: int = 8) -> str:
    t = unicodedata.normalize("NFKD", text)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[`*_#>\[\]()]", " ", t)
    parts = [w for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9.&+-]*", t) if w.lower() not in
             ("the", "a", "an", "of", "for", "and", "to", "in", "on", "what", "is", "it", "this", "digest", "der",
              "die", "das", "und", "fur", "von", "original", "rendition", "not")]
    return "_".join(parts[:words]).strip("._-")


def suggest(row: sqlite3.Row) -> tuple[str | None, float, list[str]]:
    """-> (better name or None, certainty 0..1, what is missing for 90 %)."""
    purpose = (row["purpose"] or "").strip()
    missing, score = [], 0.0
    day = row["doc_date"] if row["doc_date"] and re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["doc_date"]) else None
    if day:
        score += 0.30
    else:
        missing.append("the document's date")
    if row["has_digest"] or (row["ext"] or "").lower() in (".md", ".txt", ".csv", ".json", ".html", ".eml"):
        score += 0.30                       # a text file is read directly; anything else needs its digest
    else:
        missing.append("a digest (the file was not read)")
    described = len(re.findall(r"[^\W\d_]{3,}", purpose)) >= 4
    if described:
        score += 0.20
    else:
        missing.append("a line that says what it is")
    if any(k in purpose.lower() for k in KINDS):
        score += 0.10
    else:
        missing.append("the kind of document")
    if re.search(r"\b[A-Z][\w&.-]+(?: [A-Z][\w&.-]+)*\b", purpose[1:]):
        score += 0.10
    else:
        missing.append("the party")
    if not described:
        return None, round(score, 2), missing
    body = slug(purpose)
    if not body:
        return None, round(score, 2), missing
    name = (f"{day}_" if day and not body.startswith(day) else "") + body + (row["ext"] or "")
    return name, round(score, 2), missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--print", action="store_true", dest="show")
    ap.add_argument("--min", type=float, default=0.0)
    a = ap.parse_args()
    if not DB.is_file():
        sys.exit("index missing: run python3 tools/index/refresh.py")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows, by_area = [], {}
    for r in con.execute("SELECT path, name, ext, kind, area, tier, purpose, doc_date, has_digest FROM files ORDER BY path"):
        path = r["path"]
        if any(part in path for part in SKIP_PARTS) or (r["tier"] == "archive"):
            continue
        if r["name"].endswith(".digest.md") or r["kind"] in ("digest", "summary", "manifest", "identity-excluded"):
            continue
        ext = r["ext"] or ""
        stem = r["name"][: -len(ext)] if ext and r["name"].endswith(ext) else r["name"]
        why = poor(stem)
        if not why:
            continue
        better, sure, missing = suggest(r)
        sure = min(sure, 0.80)              # a script has not read the document: 90 % is a reader's call
        if sure < a.min:
            continue
        original = r["kind"] in ORIGINAL_KINDS
        if better:
            action = ("a starting point; read the document, then rename if 90 % certain"
                      + (" (not known to the index: " + ", ".join(missing) + ")" if missing else ""))
        else:
            action = "read it first: " + ", ".join(missing)
        rows.append((path, "original" if original else "brain file", why, better or "", sure, action))
        by_area[r["area"] or "other"] = by_area.get(r["area"] or "other", 0) + 1
    ready = sum(1 for x in rows if x[3])
    head = [f"# Names that explain nothing: suggestions",
            "", f"Generated {date.today().isoformat()} by `tools/vault_health/name_check.py` from the index. Proposes only; "
            "rule: `AGENTS.md`, \"A name must explain the file\". Certainty is a mechanical estimate; whoever files a document has read it and decides.",
            "", f"**{len(rows)} files** have a name that explains nothing; for **{ready}** the index offers a starting point. "
            "By area: " + (", ".join(f"{k} {v}" for k, v in sorted(by_area.items(), key=lambda kv: -kv[1])) or "none") + ".",
            "", "| File | Kind | Why the name is poor | Better name | Certainty | What to do |", "|---|---|---|---|---|---|"]
    body = [f"| `{p}` | {k} | {w} | {('`' + b + '`') if b else ''} | {int(s * 100)} % | {act} |"
            for p, k, w, b, s, act in sorted(rows, key=lambda x: (-x[4], x[0]))]
    text = "\n".join(head + body) + "\n"
    if a.show:
        print(text)
    else:
        OUT.write_text(text, encoding="utf-8")
    print(f"{len(rows)} poor names, {ready} with a starting point from the index"
          + ("" if a.show else f"; written to {OUT.relative_to(ROOT)}"), file=sys.stderr if a.show else sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
