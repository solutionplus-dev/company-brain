"""01_Clients/CLIENTS.json -> client records (one per engagement).

Source: 01_Clients/CLIENTS.json, key "clients"
  ref          slug
  title        name, verbatim
  client       slug (the record is its own client)
  company      billing_entity: an entity code in any case (de -> DE); undecided, none or anything else -> none
  status       stage
  date         updated (ISO, or dd.mm.yyyy; other text goes to extra.date_text)
  extra        billing_entity (verbatim), kind, date_text
The contacts list of each client is NOT copied: it holds personal names and e-mail addresses.
(The record kind is 'client'.)
"""

import json

import common as C

NAME = 'clients'
KINDS = ('client',)
REQUIRED = ('01_Clients/CLIENTS.json',)
OPTIONAL = ()


def rows(vault_root):
    rel = REQUIRED[0]
    lines = C.read_text(vault_root, rel)
    data = json.loads('\n'.join(lines))
    for client in data.get('clients', []):
        slug = client.get('slug')
        yield C.rec('client', rel, C.line_of(lines, '"slug": "%s"' % slug),
                    company=C.billing_company(client.get('billing_entity')),
                    ref=slug,
                    title=client.get('name'),
                    date=C.iso_date(client.get('updated')),
                    client=slug,
                    status=client.get('stage'),
                    extra={'billing_entity': client.get('billing_entity'),
                           'kind': client.get('kind'),
                           'date_text': C.unparsed_date(client.get('updated'))})


def expected(vault_root):
    text = '\n'.join(C.read_text(vault_root, REQUIRED[0]))
    return {'client': text.count('"slug":')}
