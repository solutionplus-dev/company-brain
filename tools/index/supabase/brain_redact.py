#!/usr/bin/env python3
"""Redaction for text that leaves this computer for the Supabase brain store.

redact(text) -> (text, n_changes)      same signature as tools/index/embed/redact.py

Two layers, applied in this order:
  1. BASE: tools/index/embed/redact.py (the embeddings lane: IBAN with valid check digits, birth
     dates after born/geboren/DOB, the token after password/Passwort/Legitimierungs/
     Aktivierungscode/PIN, phone numbers, private mail addresses). If that file cannot be imported,
     the fallback copies below cover the same classes, so redaction never drops to nothing.
  2. EXTRA (always): what the base does not cover:
       card numbers (13-19 digits passing the Luhn check, or 4-4-4-4 groups);
       passport / ID / permit numbers within 30 characters after passport, Reisepass, ID,
         permit, Aufenthalt, Ausweis, visa (a token holding three or more digits);
       the identity-number formats of your own countries: regular expressions listed under
         "redact_patterns" in brain.config.json (none by default);
       the value after token, api key, secret, access key, Bearer;
       well-known key formats (Supabase, Stripe, GitHub, Slack, AWS, JWT, PEM private keys);
       phone numbers written with a 00 international prefix;
       further private mail domains (googlemail, freenet, yandex, mail.com, posteo, ...).
Kept on purpose: company register numbers (HRB 123456), invoice numbers, amounts and ordinary
dates. Bump EXTRA_VERSION when a pattern changes: it is part of REDACTION_ID, and a new
REDACTION_ID re-uploads every chunk on the next --apply.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

MARK = "[redacted]"
EXTRA_VERSION = "extra-v2"
_EMBED_DIR = Path(__file__).resolve().parents[1] / "embed"

BASE_NAME = "fallback"
BASE_VERSION = "fallback-v1"
_base = None
try:
    if (_EMBED_DIR / "redact.py").exists():
        import importlib.util
        _spec = importlib.util.spec_from_file_location("embed_redact", _EMBED_DIR / "redact.py")
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)  # stdlib-only module of the embeddings lane
        _base = _mod.redact
        BASE_NAME = "tools/index/embed/redact.py"
        BASE_VERSION = getattr(_mod, "REDACT_VERSION", "unknown")
except Exception:  # a broken base must not disable redaction: use the fallback
    _base = None

REDACTION_ID = f"{BASE_VERSION}+{EXTRA_VERSION}"

# ----------------------------------------------------------------- fallback base

_MONTHS = (r"(?:jan|feb|mar|apr|mai|may|jun|jul|aug|sep|sept|oct|okt|nov|dec|dez|januar|februar|"
           r"märz|maerz|april|juni|juli|august|september|oktober|november|dezember|january|march|"
           r"june|july|october|december)")
_DATE = (r"(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\.?\s+" + _MONTHS +
         r"\.?\s+\d{4})")
_FB_IBAN = re.compile(r"\b([A-Z]{2}\d{2})((?: ?[A-Z0-9]){11,30})\b")
_FB_BIRTH = re.compile(r"(?i)\b(geboren|geburtsdatum|geb\.|born|date of birth|dob)\b(.{0,25}?)(" + _DATE + ")")
_FB_SECRET = re.compile(r"(?i)\b(legitimierungs[- ]?id|legitimierungs\w*|aktivierungscode|freischaltcode|"
                        r"activation code|passwort|password|kennwort)\b(\s*[:=#-]?\s*)([^\s,;]+)")
_FB_PHONE_INTL = re.compile(r"(?<![\w+])\+\d{1,3}(?:[ \-]?\(?\d{1,4}\)?){3,6}(?![\w/])")
_FB_PHONE_NAT = re.compile(r"(?<![\w/.,-])0\d{1,4}(?:[ \-]\d{1,8}){1,4}(?![\w/.,-]|\d)")
_FB_EMAIL = re.compile(r"(?i)\b[\w.+%-]+@(?:gmail|web|gmx|outlook|hotmail|yahoo|icloud|me|aol|live|"
                       r"t-online|proton|protonmail)\.[a-z.]{2,6}\b")
_STOP = {"is", "the", "ist", "zu", "to", "und", "and", "wird", "für", "fuer", "for", "ein", "eine",
         "a", "an", "with", "mit", "or", "oder", "in", "im", "of", "on", "auf", "are", "sind", "was",
         "reset", "manager", "field", "feld", "policy"}


def _iban_valid(compact: str) -> bool:
    if not (15 <= len(compact) <= 34):
        return False
    try:
        num = "".join(str(int(c, 36)) for c in compact[4:] + compact[:4])
    except ValueError:
        return False
    return int(num) % 97 == 1


def _digits(s: str) -> int:
    return sum(ch.isdigit() for ch in s)


def _sub_counted(rx, fn, text):
    n = 0

    def inner(m):
        nonlocal n
        out = fn(m)
        if out != m.group(0):
            n += 1
        return out
    return rx.sub(inner, text), n


def _fallback_base(text: str) -> tuple[str, int]:
    total = 0
    steps = [
        (_FB_IBAN, lambda m: MARK if _iban_valid((m.group(1) + m.group(2)).replace(" ", "")) else m.group(0)),
        (_FB_BIRTH, lambda m: m.group(1) + m.group(2) + MARK),
        (_FB_SECRET, lambda m: m.group(0) if m.group(3).lower().strip(".:,") in _STOP
         else m.group(1) + m.group(2) + MARK),
        (_FB_EMAIL, lambda m: MARK),
        (_FB_PHONE_INTL, lambda m: MARK if 8 <= _digits(m.group(0)) <= 15 else m.group(0)),
        (_FB_PHONE_NAT, lambda m: MARK if 9 <= _digits(m.group(0)) <= 13 else m.group(0)),
    ]
    for rx, fn in steps:
        text, k = _sub_counted(rx, fn, text)
        total += k
    return text, total


# ----------------------------------------------------------------- extra layer

_PEM = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S)
_KEY_FORMATS = re.compile(
    r"\b(?:sb_secret_[A-Za-z0-9_-]{8,}|sb_publishable_[A-Za-z0-9_-]{8,}|sk_(?:live|test)_[A-Za-z0-9]{8,}"
    r"|rk_(?:live|test)_[A-Za-z0-9]{8,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}"
    r"|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})")
_BEARER = re.compile(r"(?i)\b(bearer)(\s+)([A-Za-z0-9._~+/=-]{16,})")
_TOKEN_KW = re.compile(
    r"(?i)\b(token|api[ _-]?key|apikey|client[ _-]?secret|secret[ _-]?key|secret|access[ _-]?key|"
    r"zugangscode|zugangsdaten)\b(\s*[:=]\s*|\s+)([^\s,;]+)")


def _config_patterns() -> list:
    """Extra patterns from brain.config.json ("redact_patterns": ["<regex>", ...]). A bad one is skipped."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import brainconfig
        raw = brainconfig.load().get("redact_patterns") or []
    except Exception:
        return []
    out = []
    for pattern in raw:
        try:
            out.append(re.compile(pattern))
        except (re.error, TypeError):
            continue
    return out


_CONFIG_PATTERNS = _config_patterns()
_ID_KW = re.compile(
    r"(?i)\b(passport|passnummer|pass-?nr\.?|reisepass\w*|personalausweis\w*|ausweis\w*|national id|identity number|"
    r"permit|aufenthalt\w*|visa|uid)\b"
    r"|\b(ID|Id)\b")
_ID_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9/-]{4,24}[A-Za-z0-9]")
_CARD = re.compile(r"(?<![\w.,-])(?:\d[ -]?){12,18}\d(?![\w.,-]|\d)")
_CARD_GROUPS = re.compile(r"(?<![\w.,-])\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{4}(?:[ -]\d{1,3})?(?![\w.,-]|\d)")
_PHONE_00 = re.compile(r"(?<![\w+./-])00[1-9]\d{0,2}(?:[ \-/]?\(?\d{1,5}\)?){2,6}(?![\w/.,-]|\d)")
_EMAIL_EXTRA = re.compile(r"(?i)\b[\w.+%-]+@(?:googlemail|freenet|yandex|mail|ymail|rocketmail|"
                          r"msn|posteo|mailbox|arcor|tutanota|tuta|zoho|duck)\.[a-z.]{2,6}\b")
_TOKEN_STOP = _STOP | {"budget", "budgets", "count", "counts", "usage", "limit", "limits", "window",
                       "cost", "costs", "price", "per", "refresh", "expiry", "expired", "valid",
                       "gültig", "list", "design", "tokens", "based", "auth", "type", "redacted"}
_KEEP_PREFIX = re.compile(r"(?i)^(?:INV|RE|RG|EXP|DEC|REC|OP|CR|HRB|EST|AR)(?:\b|[-_])")


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def _token_repl(m):
    val = m.group(3)
    low = val.lower().strip(".:,()[]")
    if val.startswith(MARK) or low in _TOKEN_STOP:
        return m.group(0)
    assigned = any(c in m.group(2) for c in ":=")
    looks_secret = len(val) >= 6 and (any(c.isdigit() for c in val) or len(val) >= 16)
    if assigned or looks_secret:
        return m.group(1) + m.group(2) + MARK
    return m.group(0)


def _card_repl(m):
    d = re.sub(r"\D", "", m.group(0))
    return MARK if 13 <= len(d) <= 19 and _luhn(d) else m.group(0)


def _ids_near_keywords(text: str) -> tuple[str, int]:
    out, pos, n = [], 0, 0
    for m in _ID_KW.finditer(text):
        if m.start() < pos:
            continue
        start = m.end()
        window = text[start:start + 30].split("\n", 1)[0]
        for t in _ID_TOKEN.finditer(window):
            tok = t.group(0)
            if _KEEP_PREFIX.match(tok) or "redacted" in tok:
                continue
            if _digits(tok) >= 3 and not re.fullmatch(r"(?:19|20)\d\d", tok):
                a, b = start + t.start(), start + t.end()
                out.append(text[pos:a])
                out.append(MARK)
                pos = b
                n += 1
                break
    if not out:
        return text, 0
    out.append(text[pos:])
    return "".join(out), n


def _extra(text: str) -> tuple[str, int]:
    total = 0
    for rx, fn in [
        (_PEM, lambda m: MARK),
        (_KEY_FORMATS, lambda m: MARK),
        (_BEARER, lambda m: m.group(1) + m.group(2) + MARK),
        (_TOKEN_KW, _token_repl),
        *[(rx, lambda m: MARK) for rx in _CONFIG_PATTERNS],
    ]:
        text, k = _sub_counted(rx, fn, text)
        total += k
    text, k = _ids_near_keywords(text)
    total += k
    for rx, fn in [
        (_CARD_GROUPS, lambda m: MARK),
        (_CARD, _card_repl),
        (_PHONE_00, lambda m: MARK if 9 <= _digits(m.group(0)) <= 15 else m.group(0)),
        (_EMAIL_EXTRA, lambda m: MARK),
    ]:
        text, k = _sub_counted(rx, fn, text)
        total += k
    return text, total


def redact(text: str) -> tuple[str, int]:
    """Return (redacted text, number of substitutions): base layer, then the extra layer."""
    if not text:
        return text, 0
    base = _base or _fallback_base
    try:
        t, n1 = base(text)
    except Exception:
        t, n1 = _fallback_base(text)
    t, n2 = _extra(t)
    return t, n1 + n2


def describe() -> str:
    return f"base={BASE_NAME} ({BASE_VERSION}), extra={EXTRA_VERSION}"


if __name__ == "__main__":
    data = sys.stdin.read()
    out, k = redact(data)
    sys.stdout.write(out)
    sys.stderr.write(f"{k} substitutions ({describe()})\n")
