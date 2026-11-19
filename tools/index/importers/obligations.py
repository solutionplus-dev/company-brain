"""finance/OBLIGATIONS.md -> deadline records (one per recurring obligation row).

Source: the tables under the section headings "A. ...", "B. ..." (one per entity, in the order of
brain.config.json) and a last section for obligations that concern more than one entity.
Each table has the header | # | Obligation | How often | Next known date | Status | Source file | Mail signal |.
Rows whose # is a capital letter and a number (A1, B7, C2) are records; the header and any other rows are not.
  ref          the # cell (A1, B7 ...)
  title        the Obligation cell, verbatim
  company      from the section letter: first entity, second entity, ...; the letter after the last entity -> both
  due_date     the Next known date, only when that cell holds exactly one date (ISO or dd.mm.yyyy).
               A cell with two dates, a month only, or no date gives NULL; the text stays in extra
  certainty    the Status cell's label: 'CONFIRMED' or 'NEEDS VERIFICATION' when it starts that way,
               otherwise the status text before its first parenthesis (backticks removed)
  extra        recurrence (How often), signal (Mail signal), source_file, next_known (verbatim),
               status_text (verbatim), approximate (true when the next date is marked ≈),
               section, generated_on (front matter of the file)
The file is optional: when it is absent this module yields nothing and the deadline kind keeps
its DEADLINES.md rows.
"""

import re

import common as C

NAME = 'obligations'
KINDS = ('deadline',)
REQUIRED = ()
OPTIONAL = ('finance/OBLIGATIONS.md',)

_LETTERS = 'ABCDEFGHIJ'
_SECTION = {_LETTERS[i]: code for i, code in enumerate(C.CODES[:9])}
_SECTION[_LETTERS[min(len(C.CODES), 9)]] = 'both'
_ID = re.compile(r'^[A-J]\d+$')
_DATE = re.compile(r'\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4}')
_GENERATED = re.compile(r'^generated_on:\s*(\S+)')


def _certainty(status):
    text = (status or '').replace('`', '').strip()
    for label in ('CONFIRMED', 'NEEDS VERIFICATION'):
        if text.startswith(label):
            return label
    return text.split('(')[0].strip() or None


def rows(vault_root):
    rel = OPTIONAL[0]
    try:
        lines = C.read_text(vault_root, rel)
    except OSError:
        return
    generated = None
    for line in lines[:8]:
        match = _GENERATED.match(line)
        if match:
            generated = match.group(1)
    for table in C.md_tables(lines):
        header = [h.lower() for h in table['header']]
        if table['header'][:2] != ['#', 'Obligation'] or 'next known date' not in header:
            continue
        section_match = re.match(r'^([A-J])\.', table['heading'] or '')
        company = _SECTION.get(section_match.group(1)) if section_match else None
        if company is None:
            C.log('obligations: table at line %d has no lettered section (A., B., ...); company none' % table['start'])
            company = 'none'
        for line_no, cells in table['rows']:
            values, short = C.cell_map(table['header'], cells)
            ref = (values.get('#') or '').replace('**', '').strip()
            if not _ID.match(ref):
                continue
            next_known = values.get('next known date') or ''
            dates = _DATE.findall(next_known)
            due = C.iso_date(dates[0]) if len(dates) == 1 else None
            status = values.get('status') or ''
            yield C.rec('deadline', rel, line_no,
                        company=company,
                        ref=ref,
                        title=values.get('obligation') or None,
                        due_date=due,
                        certainty=_certainty(status),
                        extra={
                            'recurrence': values.get('how often') or None,
                            'signal': values.get('mail signal') or None,
                            'source_file': values.get('source file') or None,
                            'next_known': next_known or None,
                            'status_text': status or None,
                            'approximate': True if '≈' in next_known else None,
                            'section': table['heading'],
                            'generated_on': generated,
                            'parse_note': ('row has %d cells for %d columns' % (len(cells), len(header))
                                           if short else None),
                        })


def expected(vault_root):
    """Independent count: table rows whose first cell is an id (one to three capital letters and a number)."""
    count = 0
    for rel in OPTIONAL:
        try:
            lines = C.read_text(vault_root, rel)
        except OSError:
            continue
        count += sum(1 for line in lines if re.match(r'^\|\s*[A-Z]{1,3}\d+\s*\|', line))
    return {'deadline': count}
