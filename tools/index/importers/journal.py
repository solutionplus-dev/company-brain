"""finance/ledger/<CODE>/journal*.csv -> ledger_line records (one per journal line).

Source: every CSV whose name starts with "journal" in finance/ledger/<CODE>/, where <CODE> is an
entity code from brain.config.json. One folder per legal entity, so a file can never hold two.
Header (these names, any order; extra columns are ignored):
  jnl,date,account,account_name,description,debit,credit,currency,counterparty,source,certainty
  ref          jnl, the journal entry number as written
  title        description, verbatim
  date         date (ISO, or dd.mm.yyyy; other text goes to extra.date_text)
  company      the entity code of the folder
  amount       the debit cell, or the credit cell when the debit is empty or zero; amount_text keeps the text
  currency     the row's own currency (three capital letters); never converted
  counterparty verbatim
  certainty    the row's own label (statement / proof / calculated / booked / unverified / unknown)
  extra        account, account_name, debit, credit, side, source (the document that proves the line),
               date_text, parse_note
Nothing is summed. A reader sums one entity and one currency at a time.
"""
import os

import common as C

NAME = 'journal'
KINDS = ('ledger_line',)
REQUIRED = ()
OPTIONAL = ()


def _files(vault_root):
    for code in C.CODES:
        folder = C.path_in(vault_root, 'finance/ledger/%s' % code)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if name.startswith('journal') and name.endswith('.csv'):
                yield code, 'finance/ledger/%s/%s' % (code, name)


def _clean(value):
    value = (value or '').strip()
    return value or None


def rows(vault_root):
    for code, rel in _files(vault_root):
        for header, cells, line_no, note in C.read_journal(vault_root, rel):
            col = dict(zip([h.strip() for h in header], cells))
            debit, debit_text = C.amount_pair(col.get('debit'))
            credit, credit_text = C.amount_pair(col.get('credit'))
            if debit not in (None, 0.0) or credit in (None, 0.0):
                amount, amount_text, side = debit, debit_text, 'debit'
            else:
                amount, amount_text, side = credit, credit_text, 'credit'
            currency = (col.get('currency') or '').strip().upper() or None
            yield C.rec('ledger_line', rel, line_no,
                        company=code,
                        ref=_clean(col.get('jnl')),
                        title=col.get('description'),
                        date=C.iso_date(col.get('date')),
                        amount=amount,
                        amount_text=amount_text,
                        currency=currency,
                        counterparty=_clean(col.get('counterparty')),
                        certainty=_clean(col.get('certainty')),
                        extra={'account': _clean(col.get('account')),
                               'account_name': _clean(col.get('account_name')),
                               'debit': debit_text,
                               'credit': credit_text,
                               'side': side,
                               'source': _clean(col.get('source')),
                               'date_text': C.unparsed_date(col.get('date')),
                               'parse_note': note})


def expected(vault_root):
    count = 0
    for _code, rel in _files(vault_root):
        lines = C.read_text(vault_root, rel)
        count += sum(1 for line in lines[1:] if line.strip())
    return {'ledger_line': count}


def checks(vault_root):
    """Report-only checks, nothing stored. Per file: rows without an amount, rows with both sides
    filled, rows without a currency, rows without a source document, and journal entries whose debits
    and credits differ (compared per entry and per currency, as written)."""
    out = {'row without an amount': [], 'row with debit and credit': [], 'row without a currency': [],
           'row without a source document': [], 'entry not balanced': []}
    for _code, rel in _files(vault_root):
        totals = {}
        for header, cells, line_no, _note in C.read_journal(vault_root, rel):
            col = dict(zip([h.strip() for h in header], cells))
            where = '%s:%d %s' % (rel, line_no, _clean(col.get('jnl')) or '')
            debit, _ = C.amount_pair(col.get('debit'))
            credit, _ = C.amount_pair(col.get('credit'))
            if debit in (None, 0.0) and credit in (None, 0.0):
                out['row without an amount'].append(where)
            if debit not in (None, 0.0) and credit not in (None, 0.0):
                out['row with debit and credit'].append(where)
            if not _clean(col.get('currency')):
                out['row without a currency'].append(where)
            if not _clean(col.get('source')):
                out['row without a source document'].append(where)
            key = (_clean(col.get('jnl')), (col.get('currency') or '').strip().upper())
            sides = totals.setdefault(key, [0, 0])
            sides[0] += int(round((debit or 0.0) * 100))
            sides[1] += int(round((credit or 0.0) * 100))
        for (jnl, currency), (deb, cred) in sorted(totals.items(), key=lambda kv: str(kv[0])):
            if deb != cred:
                out['entry not balanced'].append('%s %s %s: debit %.2f, credit %.2f'
                                                 % (rel, jnl, currency, deb / 100, cred / 100))
    return out
