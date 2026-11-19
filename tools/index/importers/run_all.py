#!/usr/bin/env python3
"""Build the `records` table from the vault's business registers (see docs/SEARCH_AND_EMBEDDINGS.md).

Usage
  python3 tools/index/importers/run_all.py --db <path> [--check] [--vault <root>]
  from run_all import run; run(db_path, vault_root=None) -> int   (rows inserted)

How a run works
  - CREATE TABLE IF NOT EXISTS records (the definition in tools/index/migrate.py).
  - Each importer module is read. A REQUIRED source that is missing, or a module that raises,
    is logged and the module is skipped. A missing OPTIONAL source is logged and ignored.
  - A kind is replaced only when every module that declares it was read. Then, in one
    transaction, its old rows are deleted and the fresh rows inserted (INSERT OR IGNORE, so a
    duplicate key is counted and reported, never silently merged). A kind whose source is missing
    keeps its existing rows.
  - --check prints, per module and kind, the independent count of the source against the rows
    produced, then the table counts, then the flags (both-company rows, amounts without a
    currency, unparsed dates, duplicate keys, '@' in a value).
"""

import argparse
import collections
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import common as C  # noqa: E402
import journal  # noqa: E402
import meetings  # noqa: E402
import decisions  # noqa: E402
import deadlines  # noqa: E402
import todos  # noqa: E402
import recommendations  # noqa: E402
import clients  # noqa: E402
import people  # noqa: E402
import obligations  # noqa: E402

MODULES = (journal, meetings, decisions, deadlines, obligations, todos, recommendations,
           clients, people)
DEFAULT_VAULT = os.path.abspath(os.environ.get('BRAIN_ROOT') or os.path.join(HERE, '..', '..', '..'))

DDL = """CREATE TABLE IF NOT EXISTS records(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, company TEXT, ref TEXT, title TEXT,
  date TEXT, due_date TEXT, amount REAL, amount_text TEXT, currency TEXT,
  counterparty TEXT, status TEXT, certainty TEXT, client TEXT,
  source_path TEXT NOT NULL, source_line INTEGER, extra TEXT, imported_at TEXT,
  UNIQUE(kind, ref, source_path, source_line));"""

INSERT_SQL = ('INSERT OR IGNORE INTO records (' + ', '.join(C.COLUMNS) + ', imported_at) '
              'VALUES (' + ', '.join(['?'] * (len(C.COLUMNS) + 1)) + ')')


def _ready(vault_root, module):
    ok = True
    for rel in module.REQUIRED:
        if not os.path.isfile(C.path_in(vault_root, rel)):
            C.log('%s: required source missing, module skipped: %s' % (module.NAME, rel))
            ok = False
    for rel in module.OPTIONAL:
        if not os.path.isfile(C.path_in(vault_root, rel)):
            C.log('%s: optional source not present, carried on without it: %s' % (module.NAME, rel))
    return ok


def run_detail(db_path, vault_root=None):
    vault_root = os.path.abspath(vault_root or DEFAULT_VAULT)
    del C.LOG[:]
    C.REDACTIONS.clear()
    C.KEPT_DOMAINS.clear()
    ready = {m.NAME: _ready(vault_root, m) for m in MODULES}

    produced = {}
    for module in MODULES:
        if not ready[module.NAME]:
            continue
        try:
            produced[module.NAME] = list(module.rows(vault_root))
        except Exception as exc:  # a changed format must not half-write the table
            C.log('%s: failed while reading, module skipped: %r' % (module.NAME, exc))
            ready[module.NAME] = False

    all_kinds = sorted({k for m in MODULES for k in m.KINDS})
    replace = [k for k in all_kinds
               if all(ready[m.NAME] for m in MODULES if k in m.KINDS)]
    skipped = [k for k in all_kinds if k not in replace]
    for kind in skipped:
        C.log('kind %s not replaced: a source it needs is missing or failed; existing rows kept' % kind)

    expected = {}
    for module in MODULES:
        if not ready[module.NAME]:
            continue
        try:
            expected[module.NAME] = module.expected(vault_root)
        except Exception as exc:
            C.log('%s: expected count failed: %r' % (module.NAME, exc))
            expected[module.NAME] = None

    to_write = []
    for module in MODULES:
        for row in produced.get(module.NAME, []):
            if row['kind'] in replace:
                to_write.append((module.NAME, row))

    stamp = C.now_utc()
    inserted = collections.Counter()
    ignored = []
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.execute(DDL)
        conn.execute('BEGIN')
        try:
            for kind in replace:
                conn.execute('DELETE FROM records WHERE kind = ?', (kind,))
            for module_name, row in to_write:
                values = [row[c] for c in C.COLUMNS] + [stamp]
                cur = conn.execute(INSERT_SQL, values)
                if cur.rowcount:
                    inserted[row['kind']] += 1
                else:
                    ignored.append((module_name, row['kind'], row['ref'],
                                    row['source_path'], row['source_line']))
            conn.execute('COMMIT')
        except Exception:
            conn.execute('ROLLBACK')
            raise
        db_counts = {}
        for kind, company, n in conn.execute(
                'SELECT kind, company, COUNT(*) FROM records GROUP BY kind, company'):
            db_counts.setdefault(kind, collections.Counter())[company] = n
        # rows whose source file is no longer at that path (a moved or deleted source): kept, and flagged
        stale = {}
        for path, n in conn.execute('SELECT source_path, COUNT(*) FROM records GROUP BY source_path'):
            if not os.path.exists(C.path_in(vault_root, path)):
                stale[path] = n
    finally:
        conn.close()

    return {
        'ready': ready,
        'replace': replace,
        'skipped': skipped,
        'produced': {name: collections.Counter(r['kind'] for r in rows)
                     for name, rows in produced.items()},
        'rows': produced,
        'expected': expected,
        'inserted': inserted,
        'ignored': ignored,
        'db_counts': db_counts,
        'stale': stale,
        'total': sum(inserted.values()),
        'log': list(C.LOG),
    }


def run(db_path, vault_root=None):
    """Replace the records of every kind whose sources are readable. Returns rows inserted."""
    return run_detail(db_path, vault_root)['total']


def _flags(detail):
    """Summary lines: a count per category, the first examples, and the business domains kept."""
    groups = collections.OrderedDict()

    def add(category, example):
        groups.setdefault(category, []).append(example)

    for item in detail['ignored']:
        add('duplicate key ignored (kind, ref, source, line)', '%s %s %s:%s' % (item[1], item[2], item[3], item[4]))
    for name, rows in detail['rows'].items():
        for row in rows:
            if row['kind'] not in detail['replace']:
                continue
            where = '%s %s (%s)' % (row['kind'], row['ref'], name)
            if row['amount_text'] is not None and row['amount'] is None:
                add('amount text not a plain decimal (kept as text)', where + ' ' + repr(row['amount_text']))
            if row['amount'] is not None and not row['currency']:
                add('amount without currency', where)
            if row['company'] == 'both':
                add('row naming both companies (company both)', where)
            elif len(set(C.mentions(row['title']))) > 1:
                add('title names both companies (company kept as stated)', where)
            if row['extra'] and '"date_text"' in row['extra']:
                add('date text not ISO or dd.mm.yyyy (kept in extra)', where)
    for path, n in sorted(detail['stale'].items()):
        add('rows whose source file is not at that path any more (kept until the source returns)',
            '%s: %d rows' % (path, n))
    lines = []
    for category, examples in groups.items():
        lines.append('%s: %d' % (category, len(examples)))
        for example in examples[:6]:
            lines.append('     ' + example)
    if C.REDACTIONS:
        lines.append('private e-mail addresses redacted (by domain): %s'
                     % ', '.join('%s %d' % kv for kv in C.REDACTIONS.most_common()))
    if C.KEPT_DOMAINS:
        lines.append('business e-mail domains kept in values (count): %s'
                     % ', '.join('%s %d' % kv for kv in C.KEPT_DOMAINS.most_common()))
    return lines


def print_check(detail, vault_root):
    print('')
    print('Importer check  (expected = independent count of the source; produced = rows read)')
    print('%-17s %-14s %9s %9s  %s' % ('module', 'kind', 'expected', 'produced', 'result'))
    for module in MODULES:
        for kind in module.KINDS:
            produced = detail['produced'].get(module.NAME, collections.Counter()).get(kind, 0)
            if not detail['ready'].get(module.NAME):
                result = 'SKIPPED (source missing or failed; see log)'
                exp_text = '-'
            else:
                exp = (detail['expected'].get(module.NAME) or {}).get(kind)
                exp_text = '-' if exp is None else str(exp)
                if exp is None:
                    result = 'NO COUNT'
                elif exp == produced:
                    result = 'OK'
                else:
                    result = 'DIFF %+d (produced - expected)' % (produced - exp)
                if kind not in detail['replace']:
                    result += '  [kind not replaced, rows kept]'
            print('%-17s %-14s %9s %9s  %s' % (module.NAME, kind, exp_text, produced, result))
        if hasattr(module, 'per_file_expected') and detail['ready'].get(module.NAME):
            per_file = module.per_file_expected(vault_root)
            for rel, exp in per_file.items():
                got = sum(1 for r in detail['rows'].get(module.NAME, []) if r['source_path'] == rel)
                ok = 'OK' if got == exp else 'DIFF %+d' % (got - exp)
                print('      %-62s %9d %9d  %s' % (rel, exp, got, ok))
    print('')
    print('Records table after this run (rows per kind: company split)')
    print('%-14s %7s   %s' % ('kind', 'rows', ' / '.join(C.COMPANIES)))
    for kind in sorted(detail['db_counts']):
        counts = detail['db_counts'][kind]
        total = sum(counts.values())
        split = ' / '.join(str(counts.get(c, 0)) for c in C.COMPANIES)
        print('%-14s %7d   %s' % (kind, total, split))
    print('')
    print('Flags')
    flags = _flags(detail)
    if not flags:
        print('   none')
    for line in flags:
        print('   ' + line)
    print('')
    print('Log')
    for line in detail['log']:
        print('   ' + line)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--db', required=True, help='SQLite file to write the records table into')
    parser.add_argument('--vault', default=DEFAULT_VAULT, help='vault root (default: this repository)')
    parser.add_argument('--check', action='store_true', help='print the per-importer count check')
    args = parser.parse_args(argv)
    detail = run_detail(args.db, args.vault)
    print('records written: %d rows (kinds replaced: %s; kinds kept: %s)'
          % (detail['total'], ', '.join(detail['replace']) or '-', ', '.join(detail['skipped']) or '-'))
    if args.check:
        print_check(detail, args.vault)
        print_journal_checks(args.vault)
    return 0


def print_journal_checks(vault_root):
    """Report-only journal checks (nothing stored): rows without an amount, both sides filled,
    entries not balancing within themselves, rows without a currency or a source document."""
    print('')
    print('Journal checks (report only; nothing is stored)')
    results = journal.checks(vault_root)
    for name, items in results.items():
        print('   %s: %d' % (name, len(items)))
        for item in items[:12]:
            print('        ' + item)
        if len(items) > 12:
            print('        ... %d more' % (len(items) - 12))


if __name__ == '__main__':
    sys.exit(main())
