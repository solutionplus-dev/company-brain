#!/usr/bin/env python3
"""Redaction applied to chunk text before it is stored in .index/vectors.db and embedded.

redact(text) -> (text, n_changes)

Replaced with "[redacted]":
  - IBAN-like strings (country code and check digits valid under ISO 13616 mod-97)
  - a date that follows geboren / geb. / born / date of birth / DOB / Geburtsdatum
    within 25 characters
  - the token after Legitimierungs-ID, Aktivierungscode, Freischaltcode, activation code,
    Passwort or password, and after an uppercase PIN (lowercase "pin" in prose is kept)
  - phone numbers: international (leading +) and national (leading 0, 9 to 13 digits)
  - private e-mail addresses (gmail, web.de, gmx, outlook, hotmail, yahoo, icloud, ...)

Kept on purpose: company register numbers (HRB ...), tax numbers, VAT IDs, invoice numbers
and amounts. Bump REDACT_VERSION whenever a pattern changes.
"""
from __future__ import annotations

import re

REDACT_VERSION = "redact-v1"
MARK = "[redacted]"

_STOP = {"is", "the", "ist", "zu", "to", "und", "and", "wird", "für", "fuer", "for", "ein",
         "eine", "a", "an", "with", "mit", "or", "oder", "in", "im", "of", "on", "auf"}

_MONTHS = (r"(?:jan|feb|mar|apr|mai|may|jun|jul|aug|sep|sept|oct|okt|nov|dec|dez|"
           r"januar|februar|märz|maerz|april|juni|juli|august|september|oktober|november|dezember|"
           r"january|march|june|july|october|december)")
_DATE = (r"(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"
         r"|\d{4}-\d{2}-\d{2}"
         r"|\d{1,2}\.?\s+" + _MONTHS + r"\.?\s+\d{4})")

_IBAN_RE = re.compile(r"\b([A-Z]{2}\d{2})((?: ?[A-Z0-9]){11,30})\b")
_BIRTH_RE = re.compile(
    r"(?i)\b(geboren|geburtsdatum|geburtstag|geb\.|geb|born|date of birth|dob)\b"
    r"(.{0,25}?)(" + _DATE + r")")
_SECRET_RE = re.compile(
    r"(?i)\b(legitimierungs[- ]?id|legitimierungs\w*|aktivierungscode|freischaltcode|"
    r"activation code|passwort|password)\b(\s*[:=#-]?\s*)([^\s,;]+)")
_PIN_RE = re.compile(r"\bPIN\b(\s*[:=#-]?\s*)([^\s,;]+)")
_PHONE_INTL = re.compile(r"(?<![\w+])\+\d{1,3}(?:[ \-]?\(?\d{1,4}\)?){3,6}(?![\w/])")
_PHONE_NAT = re.compile(r"(?<![\w/.,-])0\d{1,4}(?:[ \-]\d{1,8}){1,4}(?![\w/.,-]|\d)")
_EMAIL_RE = re.compile(
    r"(?i)\b[\w.+%-]+@(?:gmail|web|gmx|outlook|hotmail|yahoo|icloud|me|aol|live|t-online|"
    r"proton|protonmail)\.[a-z.]{2,6}\b")


def _iban_valid(compact: str) -> bool:
    if not (15 <= len(compact) <= 34):
        return False
    rearranged = compact[4:] + compact[:4]
    num = "".join(str(int(c, 36)) for c in rearranged)
    return int(num) % 97 == 1


def _digits(s: str) -> int:
    return sum(ch.isdigit() for ch in s)


def redact(text: str) -> tuple[str, int]:
    """Return (redacted text, number of substitutions)."""
    n = 0

    # IBAN: only when the check digits validate, so invoice and tax numbers stay
    def iban_repl(m: re.Match) -> str:
        nonlocal n
        if _iban_valid((m.group(1) + m.group(2)).replace(" ", "")):
            n += 1
            return MARK
        return m.group(0)

    text = _IBAN_RE.sub(iban_repl, text)

    def counted(repl):
        def inner(m: re.Match) -> str:
            nonlocal n
            n += 1
            return repl(m)
        return inner

    # birth date after a birth keyword
    text = _BIRTH_RE.sub(counted(lambda m: m.group(1) + m.group(2) + MARK), text)

    # secret token after the keyword (common stop words are kept)
    def secret_repl(m: re.Match) -> str:
        nonlocal n
        if m.group(3).lower().strip(".:,") in _STOP:
            return m.group(0)
        n += 1
        return m.group(1) + m.group(2) + MARK

    text = _SECRET_RE.sub(secret_repl, text)
    text = _PIN_RE.sub(counted(lambda m: "PIN" + m.group(1) + MARK), text)

    text = _EMAIL_RE.sub(counted(lambda m: MARK), text)

    # phone numbers: require 8 or more digits so dates and short codes stay
    def phone_repl(min_digits: int, max_digits: int):
        def inner(m: re.Match) -> str:
            nonlocal n
            d = _digits(m.group(0))
            if min_digits <= d <= max_digits:
                n += 1
                return MARK
            return m.group(0)
        return inner

    text = _PHONE_INTL.sub(phone_repl(8, 15), text)
    text = _PHONE_NAT.sub(phone_repl(9, 13), text)
    return text, n
