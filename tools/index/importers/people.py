"""00_Brain/PEOPLE.md -> person records (one per table row, four table kinds).

Tables recognised by their header cells; any other table in the file is not read.
  Team                  | Name | Org / entity | Role | ...      -> company from the Org cell (an entity code, or both)
  Client contacts       | Client (slug) | Name | Role | ...    -> client = slug; company none
  Vendors and advisors  | Name / org | Role for us | ...        -> company none
  Authorities           | Authority | Entity | Matter | ...    -> role none; company from Entity
  ref, title   the name, with ** and backticks removed (everything else verbatim)
  company      see above; 'none' when the register does not name our company. The Org cell is
               read only for this; it is not copied
  client       slug (client contacts only)
  extra        section, role (Role, or Role for us for vendors; none for authorities),
               org (verbatim, authorities only), matter and status (authorities)
Business e-mail, contact, source and relationship columns are NOT copied.
"""

import common as C

NAME = 'people'
KINDS = ('person',)
REQUIRED = ('00_Brain/PEOPLE.md',)
OPTIONAL = ()


def _clean(text):
    return (text or '').replace('**', '').replace('`', '').strip() or None


def rows(vault_root):
    rel = REQUIRED[0]
    lines = C.read_text(vault_root, rel)
    for table in C.md_tables(lines):
        header = [h.lower() for h in table['header']]
        if 'org / entity' in header and 'role' in header:
            section = 'team'
        elif 'client (slug)' in header:
            section = 'client contacts'
        elif 'name / org' in header:
            section = 'vendors and advisors'
        elif 'authority' in header:
            section = 'authorities'
        else:
            C.log('people: table at line %d not recognised, skipped' % table['start'])
            continue
        for line_no, cells in table['rows']:
            values, _ = C.cell_map(table['header'], cells)
            if section == 'team':
                org = values.get('org / entity') or None
                name = _clean(values.get('name'))
                yield C.rec('person', rel, line_no, company=C.company_of(C.mentions(org)),
                            ref=name, title=name,
                            extra={'section': section,
                                   'role': _clean(values.get('role'))})
            elif section == 'client contacts':
                name = _clean(values.get('name'))
                yield C.rec('person', rel, line_no, company='none',
                            ref=name, title=name,
                            client=_clean(values.get('client (slug)')),
                            extra={'section': section, 'role': _clean(values.get('role'))})
            elif section == 'vendors and advisors':
                name = _clean(values.get('name / org'))
                yield C.rec('person', rel, line_no, company='none',
                            ref=name, title=name,
                            extra={'section': section,
                                   'role': _clean(values.get('role for us'))})
            else:
                entity = values.get('entity') or None
                name = _clean(values.get('authority'))
                yield C.rec('person', rel, line_no,
                            company=C.company_of(C.mentions(entity)),
                            ref=name, title=name,
                            extra={'section': section, 'org': entity,
                                   'matter': values.get('matter') or None,
                                   'status': values.get('status') or None})


def expected(vault_root):
    """Independent count: lines that start with a bar, minus the separator rows and the header row
    of each table (the line above a separator)."""
    lines = C.read_text(vault_root, REQUIRED[0])
    count = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith('|'):
            continue
        following = lines[index + 1].strip() if index + 1 < len(lines) else ''
        if set(stripped.replace('|', '').replace(' ', '')) <= set('-:'):
            continue
        if following.startswith('|') and set(following.replace('|', '').replace(' ', '')) <= set('-:'):
            continue
        count += 1
    return {'person': count}
