"""Checkbox lines of the root TODO.md and 00_Brain/OPEN_LOOPS.md -> todo records.

Each line "- [ ] text", "- [x] text" or "- [~] text" (any indent, "*" also accepted) is one record.
  ref          short hash of the text after the checkbox (so ticking a box keeps the ref)
  title        the text after the checkbox, verbatim
  status       'done' for [x] / [X]; 'open' for [ ] and [~]
  company      from a label at the start of the text ("DE:", "**UK** —"); otherwise 'none'
  extra        marker (the box as written), section (nearest heading above), mentions, indent
"""

import re

import common as C

NAME = 'todos'
KINDS = ('todo',)
REQUIRED = ('TODO.md', '00_Brain/OPEN_LOOPS.md')
OPTIONAL = ()

_BOX = re.compile(r'^(\s*)[-*]\s+\[([ xX~])\]\s*(.*)$')


def rows(vault_root):
    for rel in REQUIRED:
        lines = C.read_text(vault_root, rel)
        heading = None
        for line_no, line in enumerate(lines, 1):
            if line.startswith('#'):
                heading = line.lstrip('#').strip()
                continue
            match = _BOX.match(line)
            if not match:
                continue
            indent, marker, text = match.group(1), match.group(2), match.group(3).strip()
            yield C.rec('todo', rel, line_no,
                        company=C.label_company(text),
                        ref=C.short_hash(text),
                        title=text,
                        status='done' if marker in 'xX' else 'open',
                        extra={'marker': marker, 'section': heading,
                               'mentions': C.mentions(text), 'indent': len(indent)})


def expected(vault_root):
    """Independent count: lines that start with one of the four box forms."""
    boxes = ('- [ ]', '- [x]', '- [X]', '- [~]')
    count = 0
    for rel in REQUIRED:
        lines = C.read_text(vault_root, rel)
        count += sum(1 for line in lines if line.lstrip().startswith(boxes))
    return {'todo': count}
