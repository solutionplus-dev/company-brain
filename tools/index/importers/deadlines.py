"""00_Brain/DEADLINES.md (and finance/OBLIGATIONS.md when it exists) -> deadline records.

Sources: every markdown table whose header has the cells "When" and "What".
Other tables in the same file are not deadlines and are not read.
  ref          short hash of When + What (stable while the row text is unchanged)
  title        What cell, verbatim
  due_date     When cell when it is ISO or dd.mm.yyyy and nothing else; else NULL
  company      an entity code only when the What cell opens with that label ("DE: ..."); otherwise 'none'.
               Names found in the text go to extra.mentions
  certainty    the Label or Certainty cell, verbatim (the source's own label; not mapped)
  extra        when (verbatim When cell), owner, confirmed_by / evidence, the other cells by
               their header name, section (the heading above the table), mentions, parse_note
date is NULL: a deadline has a due date, not an entry date. The section heading carries the
date the entry was written.
"""

import re

import common as C

NAME = 'deadlines'
KINDS = ('deadline',)
REQUIRED = ('00_Brain/DEADLINES.md',)
OPTIONAL = ()  # finance/OBLIGATIONS.md is read by obligations.py (its own table shape)

_HEADER = re.compile(r'\|\s*When\s*\|\s*What\s*\|')
_SEPARATOR = re.compile(r'^\|[\s|:-]*-[\s|:-]*$')


def rows(vault_root):
    for rel in REQUIRED + OPTIONAL:
        try:
            lines = C.read_text(vault_root, rel)
        except OSError:
            if rel in REQUIRED:
                raise
            continue
        for table in C.md_tables(lines):
            header = [h.lower() for h in table['header']]
            if 'when' not in header or 'what' not in header:
                continue
            for line_no, cells in table['rows']:
                values, short = C.cell_map(table['header'], cells)
                when = values.get('when', '')
                what = values.get('what', '')
                extra = {'when': when or None, 'section': table['heading']}
                for name, text in values.items():
                    if name not in ('when', 'what', 'owner', 'label', 'certainty'):
                        extra[C.header_key(name)] = text or None
                extra['owner'] = values.get('owner') or None
                extra['mentions'] = C.mentions(what)
                extra['parse_note'] = ('row has %d cells for %d columns' % (len(cells), len(header))
                                       if short else None)
                label = values.get('label') or values.get('certainty') or None
                yield C.rec('deadline', rel, line_no,
                            company=C.label_company(what),
                            ref=C.short_hash(when + '|' + what),
                            title=what or None,
                            due_date=C.iso_date(when),
                            certainty=label,
                            extra=extra)


def expected(vault_root):
    """Independent count: data lines (not the header, not the separator) under a When/What header."""
    count = 0
    for rel in REQUIRED + OPTIONAL:
        try:
            lines = C.read_text(vault_root, rel)
        except OSError:
            continue
        in_table = False
        for line in lines:
            if _HEADER.search(line) and line.lstrip().startswith('|'):
                in_table = True
                continue
            if in_table:
                if not line.lstrip().startswith('|'):
                    in_table = False
                elif not _SEPARATOR.match(line.strip()):
                    count += 1
    return {'deadline': count}
