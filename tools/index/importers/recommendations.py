"""00_Brain/RECOMMENDATIONS.md -> recommendation records (one per REC block).

A block starts with a heading of the form
  ### REC-2030-002 · U0·S1 · both (entity undecided) · sales · `key`        (open section)
  ### REC-2030-001 · done · U0·S1 · DE · collections · `key`               (closed section)
  ref          REC id
  title        the **What:** line of the block, verbatim (the key when there is none)
  company      first word of the entity text: both or an entity code; otherwise 'none'
  status       first word of the block's "- **Status:**" line (proposed, accepted, done, ...);
               when the block has no such line, the status word in the heading, else NULL
  extra        section (heading above the block), urgency_severity (U#·S#), entity (verbatim),
               category, key, status_line (verbatim), status_heading
"""

import re

import common as C

NAME = 'recommendations'
KINDS = ('recommendation',)
REQUIRED = ('00_Brain/RECOMMENDATIONS.md',)
OPTIONAL = ()

_HEADING = re.compile(r'^### (REC-\d{4}-\d{3}) · (.+)$')
_US = re.compile(r'^U\d·S\d$')
_WHAT = re.compile(r'^- \*\*What:\*\*\s*(.*)$')
_STATUS = re.compile(r'^- \*\*Status:\*\*\s*(.*)$')


def _blocks(lines):
    section = None
    current = None
    for line_no, line in enumerate(lines, 1):
        if line.startswith('## '):
            section = line[3:].strip()
            current = None
            continue
        if line.startswith('### '):
            match = _HEADING.match(line)
            if match is None:
                # "### REC-YYYY-NNN" in the file's own format note is a template, not a block
                if line.startswith('### REC-') and 'YYYY' not in line:
                    C.log('recommendations: heading not parsed at line %d' % line_no)
                current = None
                continue
            parts = [p.strip() for p in match.group(2).split(' · ')]
            current = {'line': line_no, 'id': match.group(1), 'parts': parts,
                       'section': section, 'body': []}
            yield current
            continue
        if current is not None:
            current['body'].append(line)


def rows(vault_root):
    rel = REQUIRED[0]
    lines = C.read_text(vault_root, rel)
    for block in list(_blocks(lines)):  # collect every body first: the generator fills it as it goes
        parts = list(block['parts'])
        status_heading = None
        if parts and not _US.match(parts[0]):
            status_heading = parts.pop(0)
        if len(parts) != 4:
            C.log('recommendations: %s has %d heading fields after the status' % (block['id'], len(parts)))
        us = parts[0] if len(parts) > 0 else None
        entity = parts[1] if len(parts) > 1 else None
        category = parts[2] if len(parts) > 2 else None
        key = parts[3].strip('`') if len(parts) > 3 else None

        what = None
        status_line = None
        for body_line in block['body']:
            if what is None:
                match = _WHAT.match(body_line)
                if match:
                    what = match.group(1).strip()
            if status_line is None:
                match = _STATUS.match(body_line)
                if match:
                    status_line = match.group(1).strip()
        status = None
        if status_line:
            status = status_line.split()[0].strip('.,;:()*`')
        elif status_heading:
            status = status_heading

        company_match = re.match(r'^(both|' + '|'.join(re.escape(c) for c in C.CODES) + r')\b', entity or '') if C.CODES else re.match(r'^(both)\b', entity or '')
        yield C.rec('recommendation', rel, block['line'],
                    company=company_match.group(1) if company_match else 'none',
                    ref=block['id'],
                    title=what or key,
                    status=status,
                    extra={'section': block['section'], 'urgency_severity': us,
                           'entity': entity, 'category': category, 'key': key,
                           'status_line': status_line, 'status_heading': status_heading})


def expected(vault_root):
    lines = C.read_text(vault_root, REQUIRED[0])
    return {'recommendation': sum(1 for line in lines if re.match(r'^### REC-\d{4}-\d{3} ', line))}
