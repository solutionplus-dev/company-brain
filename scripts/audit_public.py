#!/usr/bin/env python3
"""Fail if anything private is about to be published. Standard library only.

  python3 scripts/audit_public.py                      audit the files of this repository
  python3 scripts/audit_public.py --terms FILE         also fail on every private term in FILE
  python3 scripts/audit_public.py --git                also audit the commit history (see below)
  python3 scripts/audit_public.py --allow "LICENSE:Example GmbH"

Always checked, in every file that is text (whatever its extension): e-mail addresses outside reserved
example domains, phone numbers, bank account numbers (IBAN), home-folder paths, hosted-database project
addresses, long tokens and keys, ID-like numbers after words such as passport or permit.

A terms file holds what only you know is private: one term per line (your company names, register and
tax numbers, client names, every person's first name and surname on its own line, vendors, street
names, cities, project ids). Lines starting with `re:` are regular expressions; `#` starts a comment.
Keep that file OUT of the repository you are auditing. A plain term is matched on word boundaries
after both sides were normalised: case, accents, and any run of spaces, hyphens, dots or other
punctuation count as one space, so "Blue-Heron", "BLUE  HERON" and "Blue Héron" all match
"Blue Heron", also when the name is broken over two lines. A single word that is distinctive only by
its punctuation ("_Drafts") is matched as written.

Reviewed exceptions that belong to the repository (test fixtures, the licence holder) go into a file
`.audit-allow` at its root, one per line: `relative/path:the exact text that may appear there`. An
exception covers only that text, not the rest of its line. For commit identities the path is `git`:
`git:Example GmbH <hello@example.com>`.

--git reads every commit on every local and remote ref: each author, committer and Co-authored-by
identity must be listed in `.audit-allow`, and commit messages are checked like files. A web merge on a
hosting service usually records the personal name and e-mail address of whoever clicked. What this
script cannot read at all: pull-request and issue pages, their comments, and refs the hosting service
keeps. So a repository that was developed in private is published as a fresh copy with one new commit,
never by switching the old one to public.

Exit code 0 when clean, 1 when anything was found. Findings print as  path:line  kind  text.
"""
import argparse
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(os.environ.get("BRAIN_ROOT") or Path(__file__).resolve().parents[1]).resolve()
SKIP_DIRS = {".git", ".index", "__pycache__", ".venv", "node_modules"}
MAX_BYTES = 5_000_000
SAFE_MAIL = re.compile(r"@(?:[a-z0-9-]+\.)*(?:example\.(?:com|org|net)|[a-z0-9-]+\.(?:test|example|invalid))$", re.I)

BUILT_IN = [
    ("e-mail address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b")),
    ("phone number", re.compile(r"(?<![\w.+-])(?:\+|00)[1-9]\d{0,2}[ -]?(?:\(?\d{1,4}\)?[ -]?){2,5}\d{2,4}(?!\w)")),
    ("bank account number", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b")),
    ("home-folder path", re.compile(r"(?:/Users/|/home/|[A-Z]:\\Users\\)[A-Za-z0-9._-]+")),
    ("hosted database address", re.compile(r"\b[a-z0-9]{20}\.supabase\.(?:co|in)\b")),
    ("token or key", re.compile(r"\b(?:eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,}|"
                                r"gh[pousrh]_[A-Za-z0-9]{20,}|sbp_[a-f0-9]{30,}|AKIA[A-Z0-9]{16})\b")),
    ("identity number", re.compile(r"(?i)\b(?:passport|reisepass|permit|aufenthaltstitel|national id|id card)"
                                   r"\b[^\n]{0,30}?\b[A-Z0-9]{2}[A-Z0-9 -]{5,}\d\b")),
]
TRAILER = re.compile(r"(?im)^co-authored-by:\s*(.+?)\s*$")


def norm(text):
    """Case, accents and punctuation removed: what is left is words separated by single spaces."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def load_terms(path):
    """-> list of (label, kind, matcher). kind 'raw' is a regular expression on the text as written;
    kind 'norm' is a compiled pattern for normalised text."""
    terms = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("re:"):
            terms.append((line[3:].strip(), "raw", re.compile(line[3:].strip(), re.I)))
            continue
        n = norm(line)
        if not n:
            continue
        if " " not in n and re.search(r"[^\w]|_", line):
            # one word whose punctuation is what makes it distinctive ("_Drafts", ".env"): match as written
            terms.append((line, "raw", re.compile(r"(?<!\w)" + re.escape(line) + r"(?!\w)", re.I)))
        else:
            terms.append((line, "norm", re.compile(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])")))
    return terms


def files(root):
    for folder, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            if name != ".audit-allow":
                yield Path(folder) / name


def read_text(path):
    """The file's text, or None when it is not text (binary, too large, unreadable)."""
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def allowed(hit, allow_texts):
    """An exception covers a finding only when the found text lies inside the excepted text."""
    h = norm(hit)
    return any(h and h in a for a in allow_texts) or any(hit.lower() in raw for raw in allow_texts)


def check_text(rel, text, terms, allow_texts):
    out = []
    lines = text.splitlines()
    seen_terms = set()
    for no, line in enumerate(lines, 1):
        for kind, rx in BUILT_IN:
            for m in rx.finditer(line):
                hit = m.group(0)
                if kind == "e-mail address" and SAFE_MAIL.search(hit):
                    continue
                if kind == "bank account number" and not re.search(r"\d{6,}", hit.replace(" ", "")):
                    continue
                if not allowed(hit, allow_texts):
                    out.append((rel, no, kind, hit))
        nline = norm(line)
        for label, kind, rx in terms:
            found = rx.search(line) if kind == "raw" else rx.search(nline)
            if found:
                seen_terms.add(label)
                if not allowed(found.group(0) if kind == "raw" else label, allow_texts):
                    out.append((rel, no, "private term", label))
    # a name broken over two lines is found in the text as a whole
    whole = norm(text)
    for label, kind, rx in terms:
        if kind == "norm" and label not in seen_terms and rx.search(whole) and not allowed(label, allow_texts):
            out.append((rel, 0, "private term across lines", label))
    return out


def git_findings(root, terms, allow):
    """Identities and messages of every commit on every ref. -> (findings, commits read) or (None, 0)."""
    try:
        raw = subprocess.run(["git", "-C", str(root), "log", "--all", "--format=%h%x1f%an <%ae>%x1f%cn <%ce>%x1f%B%x1e"],
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None, 0
    ok_ids = {a.strip().lower() for a in allow.get("git", [])}
    out, count, reported = [], 0, set()
    for block in raw.split("\x1e"):
        block = block.strip("\n")
        if not block:
            continue
        count += 1
        sha, author, committer, message = (block.split("\x1f") + ["", "", ""])[:4]
        ids = [("author", author), ("committer", committer)] + [("co-author", t) for t in TRAILER.findall(message)]
        for role, ident in ids:
            key = ident.strip().lower()
            if key not in ok_ids and (role, key) not in reported:
                reported.add((role, key))
                out.append((f"git:{sha}", 0, f"commit identity ({role}) not in .audit-allow", ident.strip()))
        body = TRAILER.sub("", message)
        for rel, no, kind, text in check_text(f"git:{sha}", body, terms, list(ok_ids)):
            out.append((rel, no, kind + " in a commit message", text))
    return out, count


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--terms", action="append", default=[], help="file of private terms; repeatable")
    ap.add_argument("--allow", action="append", default=[], help='"relative/path:text" that may appear there; repeatable')
    ap.add_argument("--git", action="store_true", help="also audit commit identities and messages on every ref")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    terms = []
    for t in args.terms:
        terms += load_terms(t)
    allow = {}
    items = list(args.allow)
    allow_file = root / ".audit-allow"
    if allow_file.is_file():
        items += [ln.strip() for ln in allow_file.read_text(encoding="utf-8").splitlines()
                  if ln.strip() and not ln.startswith("#")]
    for item in items:
        rel, _, text = item.partition(":")
        if text.strip():
            allow.setdefault(rel, []).append(text.strip().lower())

    findings, scanned, skipped = [], 0, []
    for path in files(root):
        rel = str(path.relative_to(root))
        text = read_text(path)
        if text is None:
            skipped.append(rel)
        else:
            scanned += 1
            texts = allow.get(rel, [])
            findings += check_text(rel, text, terms, texts + [norm(t) for t in texts])
        # a private term in a file or folder name counts too, also for a file that is not text
        nrel = norm(rel)
        for label, kind, rx in terms:
            if rx.search(rel) if kind == "raw" else rx.search(nrel):
                findings.append((rel, 0, "private term in a path", label))

    commits = None
    if args.git:
        more, commits = git_findings(root, terms, allow)
        if more is None:
            findings.append(("git", 0, "history not read", "git log failed here; the history is unaudited"))
        else:
            findings += more

    for rel, no, kind, text in findings:
        print(f"{rel}:{no}  {kind}  {text}")
    for rel in skipped:
        print(f"not text, not read: {rel}")
    tail = f"\n{scanned} files read, {len(skipped)} not text, {len(terms)} private terms"
    if commits is not None:
        tail += f", {commits} commits read"
    print(f"{tail}, {len(findings)} findings.")
    if not args.git:
        print("The commit history was not read; before publishing run again with --git.")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
