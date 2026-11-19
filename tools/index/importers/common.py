"""Shared helpers for the records importers (see 00_Brain/SYSTEM/INDEX.md).

Every importer module in this folder defines:
  NAME      short name used in reports
  KINDS     record kinds the module can produce
  REQUIRED  vault-relative sources. If one is missing, the module is skipped and every kind it
            declares keeps the rows it already has in the database
  OPTIONAL  vault-relative sources. A missing one is logged and the module carries on
  rows(vault_root)      generator of dicts keyed by the records columns (absent key = NULL)
  expected(vault_root)  {kind: count} from a separate count of the source; --check compares it
                        with the rows produced

Rules every importer follows:
  - Values are copied as written. An amount is parsed only when its text is a plain decimal
    (optional minus, digits, optional dot and digits). amount_text always keeps the text. Nothing
    is converted, summed or rounded, and an amount keeps its own currency.
  - A date is stored as ISO only when the source already writes ISO or dd.mm.yyyy. Any other date
    text goes to extra.date_text and date stays NULL.
  - company is set only from a field that states it: a journal's company, a registry column, a
    label such as "DE:" at the start of an item, or the organisation named in a register column.
    Free text that merely names a company gives 'none', and the names it contains go to
    extra.mentions. A client whose name contains one of our entity codes is listed under
    not_our_entity in brain.config.json and is not counted as a mention.
  - certainty comes from a column the source has for it (deadline labels, a journal's certainty column).
    Journal rows have no certainty column, so it stays NULL and the journal's own classification
    is kept in extra.
  - source_line is the 1-based line in the source file. For JSON it is the line that holds the
    record's key.
  - No e-mail addresses, phone numbers, bank account numbers or private addresses are copied.
"""

import collections
import csv
import datetime
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import sys

COLUMNS = ('kind', 'company', 'ref', 'title', 'date', 'due_date', 'amount', 'amount_text',
           'currency', 'counterparty', 'status', 'certainty', 'client', 'source_path',
           'source_line', 'extra')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import brainconfig  # noqa: E402

CODES = brainconfig.codes()
COMPANIES = CODES + ('both', 'none')

LOG = []
REDACTIONS = collections.Counter()

# A private person's address is never copied. Addresses at a free-mail provider are private;
# addresses at a business domain (a company, a vendor, a client) are kept, as the people rule allows.
_EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)')
_FREE_MAIL = {'gmail.com', 'googlemail.com', 'outlook.com', 'hotmail.com', 'live.com', 'msn.com',
              'web.de', 'gmx.de', 'gmx.net', 'gmx.com', 'yahoo.com', 'yahoo.de', 'icloud.com',
              'me.com', 'proton.me', 'protonmail.com', 'aol.com', 't-online.de', 'mail.com'}
KEPT_DOMAINS = collections.Counter()

_ISO = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_DMY = re.compile(r'^(\d{2})\.(\d{2})\.(\d{4})$')
_PLAIN_NUM = re.compile(r'^-?\d+(\.\d+)?$')
_SEP_ROW = re.compile(r'^\|[\s:|-]*-{3,}[\s:|-]*\|?$')
_NOT_OURS = brainconfig.not_our_entity()
_ALIAS_OUT = (re.compile('|'.join(re.escape(x).replace(r'\ ', r'[ _]') for x in _NOT_OURS), re.IGNORECASE)
              if _NOT_OURS else None)
_CODE_RE = {code: re.compile(r'\b' + re.escape(code) + r'\b') for code in CODES}
_LABEL = re.compile(r'^\s*(?:\*\*)?\s*(' + '|'.join([re.escape(c) for c in CODES] + ['both'])
                    + r')\s*(?:\*\*)?\s*[:·—–]')
_BILLING = {code.lower(): code for code in CODES}


def log(message):
    LOG.append(message)
    print('[importers] ' + message, file=sys.stderr)


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def path_in(vault_root, rel):
    return os.path.join(vault_root, *rel.split('/'))


def read_text(vault_root, rel):
    """Return the file as a list of lines (1-based line n is index n-1). CRLF is normalised."""
    with open(path_in(vault_root, rel), encoding='utf-8') as handle:
        return handle.read().replace('\r\n', '\n').split('\n')


def connect_ro(path):
    """Open a SQLite file read only. The database is never written by an importer."""
    uri = pathlib.Path(path).resolve().as_uri() + '?mode=ro'
    return sqlite3.connect(uri, uri=True)


def scrub(text):
    """Replace a private (free-mail) e-mail address with a marker; keep business addresses and count them."""
    if not isinstance(text, str) or '@' not in text:
        return text

    def repl(match):
        domain = match.group(1).lower()
        if domain in _FREE_MAIL:
            REDACTIONS[domain] += 1
            return '[private e-mail redacted]'
        KEPT_DOMAINS[domain] += 1
        return match.group(0)

    return _EMAIL.sub(repl, text)


def rec(kind, source_path, source_line, **fields):
    """Build one records row. Unknown column names raise, so a typo cannot slip through."""
    row = dict.fromkeys(COLUMNS)
    row['kind'] = kind
    row['source_path'] = source_path
    row['source_line'] = source_line
    for key, value in fields.items():
        if key not in row or key in ('kind', 'source_path', 'source_line'):
            raise KeyError('not a settable column: ' + key)
        row[key] = value
    if row['company'] is None:
        row['company'] = 'none'
    if row['company'] not in COMPANIES:
        raise ValueError('bad company %r for %s %r' % (row['company'], kind, row['ref']))
    extra = row['extra']
    if isinstance(extra, dict):
        extra = {k: v for k, v in extra.items() if v not in (None, '', [], {})}
        row['extra'] = json.dumps(extra, ensure_ascii=False, sort_keys=True) if extra else None
    for key in ('ref', 'title', 'counterparty', 'status', 'certainty', 'client', 'extra'):
        row[key] = scrub(row[key])
    return row


def amount_pair(text):
    """(number, text). The number is set only when the text is a plain decimal."""
    if text is None:
        return None, None
    t = str(text).strip()
    if not t:
        return None, None
    if _PLAIN_NUM.match(t):
        return float(t), t
    return None, t


def iso_date(text):
    """ISO, or dd.mm.yyyy. Anything else returns None (the caller keeps the text in extra)."""
    if text is None:
        return None
    t = str(text).strip().replace('**', '').strip()
    if _ISO.match(t):
        try:
            return datetime.date.fromisoformat(t).isoformat()
        except ValueError:
            return None
    match = _DMY.match(t)
    if match:
        try:
            return datetime.date(int(match.group(3)), int(match.group(2)),
                                 int(match.group(1))).isoformat()
        except ValueError:
            return None
    return None


def unparsed_date(text):
    """The verbatim date text when iso_date could not read it, else None."""
    if text is None or not str(text).strip():
        return None
    return None if iso_date(text) else str(text).strip()


def mentions(text):
    """Entity codes that the text contains; phrases listed under not_our_entity are removed first."""
    if not text:
        return []
    cleaned = _ALIAS_OUT.sub(' ', str(text)) if _ALIAS_OUT else str(text)
    return [code for code in CODES if _CODE_RE[code].search(cleaned)]


def company_of(tokens):
    """Company for a field that names the organisation: one entity code, both (more than one) or none."""
    s = set(tokens) & set(CODES)
    if len(s) > 1:
        return 'both'
    if len(s) == 1:
        return next(iter(s))
    return 'none'


def label_company(text):
    """Company from a label at the start of an item ("DE: ...", "**UK** —"). Otherwise 'none'."""
    match = _LABEL.match(text or '')
    return match.group(1) if match else 'none'


def billing_company(value):
    return _BILLING.get(str(value or '').strip().lower(), 'none')


def short_hash(text):
    return hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]


def line_of(lines, needle):
    for number, line in enumerate(lines, 1):
        if needle in line:
            return number
    return None


def split_row(line):
    """Cells of one markdown table row. Escaped pipes are kept as pipes."""
    s = line.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|') and not s.endswith('\\|'):
        s = s[:-1]
    return [cell.strip().replace('\\|', '|') for cell in re.split(r'(?<!\\)\|', s)]


def md_tables(lines):
    """Yield every markdown table: {'start', 'header', 'heading', 'rows': [(line_no, cells)]}."""
    heading = None
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if line.startswith('#'):
            heading = line.lstrip('#').strip()
            i += 1
            continue
        if line.lstrip().startswith('|') and i + 1 < n and _SEP_ROW.match(lines[i + 1].strip()):
            header = split_row(line)
            rows = []
            j = i + 2
            while j < n and lines[j].lstrip().startswith('|'):
                rows.append((j + 1, split_row(lines[j])))
                j += 1
            yield {'start': i + 1, 'header': header, 'heading': heading, 'rows': rows}
            i = j
            continue
        i += 1


def header_key(name):
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


def cell_map(header, cells):
    """Map lower-cased header names to cell text. Short rows are padded with empty text."""
    keys = [h.lower() for h in header]
    padded = list(cells) + [''] * (len(keys) - len(cells))
    return {k: padded[i] for i, k in enumerate(keys)}, len(cells) != len(keys)


def read_journal(vault_root, rel):
    """Yield (header, cells, line_no, note) for each data row of a journal CSV.

    A row with more cells than the header has an unquoted comma in its last column (the source
    text). Those cells are rejoined with commas, which restores the text exactly, and the note says so.
    """
    with open(path_in(vault_root, rel), encoding='utf-8', newline='') as handle:
        reader = csv.reader(handle)
        header = next(reader)
        for cells in reader:
            line_no = reader.line_num
            if not cells or all(not c.strip() for c in cells):
                continue
            note = None
            if len(cells) > len(header):
                note = 'last column held %d unquoted comma(s); rejoined' % (len(cells) - len(header))
                cells = cells[:len(header) - 1] + [','.join(cells[len(header) - 1:])]
            elif len(cells) < len(header):
                note = 'row has %d cells for %d columns' % (len(cells), len(header))
            yield header, cells, line_no, note


def journal_expected(vault_root, rel):
    """Independent count: the account is the third field of every data line, so split on the first
    three commas only. 4xxx lines are invoices; 5xxx and 6xxx lines are expenses."""
    counts = {'invoice': 0, 'expense': 0}
    lines = read_text(vault_root, rel)
    for line in lines[1:]:
        if not line.strip():
            continue
        account = line.split(',', 3)[2].strip()
        if account.startswith('4'):
            counts['invoice'] += 1
        elif account[:1] in ('5', '6'):
            counts['expense'] += 1
    return counts


def journal_rows(vault_root, rel, company, currency, debit_col, credit_col, extra_cols):
    """Records for one journal file. Revenue (4xxx) is an invoice, cost (5xxx, 6xxx) an expense.
    Each line gives its own record; the amount is the cell of the normal side, or the other side
    when the normal side is zero."""
    for header, cells, line_no, note in read_journal(vault_root, rel):
        col = dict(zip(header, cells))
        account = col['account'].strip()
        if account.startswith('4'):
            kind, normal = 'invoice', credit_col
        elif account[:1] in ('5', '6'):
            kind, normal = 'expense', debit_col
        else:
            continue
        other = debit_col if normal == credit_col else credit_col
        normal_text = col[normal].strip()
        other_text = col[other].strip()
        normal_value, _ = amount_pair(normal_text)
        other_value, _ = amount_pair(other_text)
        chosen_col, text = normal, normal_text
        if normal_value in (None, 0.0) and other_value not in (None, 0.0):
            chosen_col, text = other, other_text
        amount, amount_text = amount_pair(text)
        extra = {
            'account': account,
            'account_name': col.get('account_name'),
            'side': 'debit' if chosen_col == debit_col else 'credit',
            'date_text': unparsed_date(col.get('date')),
            'parse_note': note,
        }
        for name in extra_cols:
            extra[name] = col.get(name)
        yield rec(kind, rel, line_no,
                  company=company,
                  ref=col['jnl'].strip(),
                  title=col.get('description'),
                  date=iso_date(col.get('date')),
                  amount=amount,
                  amount_text=amount_text,
                  currency=currency,
                  extra=extra)


def load_clients(vault_root):
    """The client list from CLIENTS.json, or [] when it is missing or unreadable (no log: callers
    that need it log the gap themselves)."""
    try:
        with open(path_in(vault_root, '01_Clients/CLIENTS.json'), encoding='utf-8') as handle:
            return json.load(handle).get('clients', [])
    except (OSError, ValueError, AttributeError):
        return []


def client_slug_for(name, clients):
    """Slug of the client whose register name equals this name, or whose name before the first
    bracket equals it ('Harbour Ltd' matches 'Harbour Ltd (in liquidation)'). Otherwise None."""
    if not name:
        return None
    key = str(name).strip().lower()
    for client in clients:
        register_name = (client.get('name') or '').strip()
        base = register_name.split(' (')[0].strip().lower()
        if key == register_name.lower() or key == base:
            return client.get('slug')
    return None


def tokens_for(company):
    if company == 'both':
        return set(CODES)
    return {company} if company in CODES else set()
