"""00_Brain/DECISIONS.md -> decision records (one per table row).

Source: the markdown table with header | ID | Date | Decision |
  ref          ID (DEC-YYYY-NNN)
  title        Decision cell, verbatim
  date         Date cell (ISO, or dd.mm.yyyy; other text goes to extra.date_text)
  company      none: the log does not state a company. Names found in the text go to extra.mentions
  extra        mentions, date_text, parse_note
Rows that name the same ID twice would be reported by the duplicate check in run_all.
"""

import common as C

NAME = 'decisions'
KINDS = ('decision',)
REQUIRED = ('00_Brain/DECISIONS.md',)
OPTIONAL = ()


def rows(vault_root):
    rel = REQUIRED[0]
    lines = C.read_text(vault_root, rel)
    for table in C.md_tables(lines):
        header = [h.lower() for h in table['header']]
        if not header or header[0] != 'id' or 'decision' not in header:
            continue
        for line_no, cells in table['rows']:
            if not cells or not cells[0].startswith('DEC-'):
                continue
            values, short = C.cell_map(table['header'], cells)
            decision = values.get('decision')
            yield C.rec('decision', rel, line_no,
                        company='none',
                        ref=cells[0].strip(),
                        title=decision,
                        date=C.iso_date(values.get('date')),
                        extra={
                            'mentions': C.mentions(decision),
                            'date_text': C.unparsed_date(values.get('date')),
                            'parse_note': 'row has %d cells for %d columns' % (len(cells), len(header))
                            if short else None,
                        })


def expected(vault_root):
    lines = C.read_text(vault_root, REQUIRED[0])
    return {'decision': sum(1 for line in lines if line.startswith('| DEC-'))}
