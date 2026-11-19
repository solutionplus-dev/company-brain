"""02_Meetings/registry.json -> meeting records (one per registry row).

Source: 02_Meetings/registry.json, key "meetings" (a list of rows)
  ref          id (the notetaker's own id, or 'manual:<date>_<slug>')
  title        title, verbatim (for excluded rows, the registry's own title and nothing else)
  date         date (ISO)
  client       client (slug as the registry writes it, or NULL)
  company      the billing entity of that client in 01_Clients/CLIENTS.json (de -> DE, uk -> UK,
               anything else -> none). Internal, prospect, vendor and excluded rows -> none.
  status       'excluded' for type excluded or external-excluded; NULL otherwise
  extra        type, platform, time_local, duration_min, provenance, has_transcript, has_notes,
               transcript_turns, path, decisions, excluded_reason, ingested, notetaker_title
Participant names and e-mail addresses are NOT copied.
"""

import json

import common as C

NAME = 'meetings'
KINDS = ('meeting',)
REQUIRED = ('02_Meetings/registry.json',)
OPTIONAL = ('01_Clients/CLIENTS.json',)
EXCLUDED = ('excluded', 'external-excluded')


def rows(vault_root):
    rel = REQUIRED[0]
    lines = C.read_text(vault_root, rel)
    data = json.loads('\n'.join(lines))
    clients = C.load_clients(vault_root)
    billing = {c.get('slug'): c.get('billing_entity') for c in clients}
    for meeting in data.get('meetings', []):
        mid = meeting.get('id')
        excluded = meeting.get('type') in EXCLUDED
        company = 'none' if excluded else C.billing_company(billing.get(meeting.get('client')))
        yield C.rec('meeting', rel, C.line_of(lines, '"id": "%s"' % mid),
                    company=company,
                    ref=mid,
                    title=meeting.get('title'),
                    date=C.iso_date(meeting.get('date')),
                    client=meeting.get('client'),
                    status='excluded' if excluded else None,
                    extra={
                        'type': meeting.get('type'),
                        'platform': meeting.get('platform'),
                        'time_local': meeting.get('time_local'),
                        'duration_min': meeting.get('duration_min'),
                        'provenance': meeting.get('provenance'),
                        'has_transcript': meeting.get('has_transcript'),
                        'has_notes': meeting.get('has_notes'),
                        'transcript_turns': meeting.get('transcript_turns'),
                        'path': meeting.get('path'),
                        'decisions': meeting.get('decisions') or None,
                        'excluded_reason': meeting.get('excluded_reason'),
                        'ingested': meeting.get('ingested'),
                        'notetaker_title': meeting.get('notetaker_title'),
                        'date_text': C.unparsed_date(meeting.get('date')),
                    })


def expected(vault_root):
    text = '\n'.join(C.read_text(vault_root, REQUIRED[0]))
    return {'meeting': text.count('"id": "')}
