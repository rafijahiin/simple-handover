"""SEMANTICS.md must stay in sync with the code it documents.

Every row of the ledger names a File and an Anchor — a verbatim string that must
still exist in that file. When someone rewrites the code that implements an
interpretive decision (CDN/FDN = slip, period = created_at, the maternal cohort,
…), the anchor disappears and this test fails, forcing them to re-confirm the
meaning and update the ledger instead of letting it drift. Silent meaning-change
is exactly how the backwards CDN/FDN split shipped.

This is deliberately a documentation-integrity test, not a behaviour test — the
behaviour is pinned by test_aggregate_coherence and the contract test.
"""
import os
import re

from django.conf import settings
from django.test import SimpleTestCase

LEDGER = os.path.join(settings.BASE_DIR, 'SEMANTICS.md')


def _rows():
    """Parse the markdown table under '## Ledger' into (key, file, anchor)."""
    text = open(LEDGER, encoding='utf-8').read()
    body = text.split('## Ledger', 1)[1]
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith('|'):
            if rows:            # table ended
                break
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        if len(cells) < 6:
            continue
        key, _decision, fname, anchor, _auth, _status = cells[:6]
        if key in ('Key', '-----') or set(key) <= {'-', ':', ' '}:
            continue            # header / separator
        rows.append((key, fname, anchor.strip('`')))
    return rows


class SemanticsLedgerTest(SimpleTestCase):
    def test_ledger_parses_and_is_non_trivial(self):
        rows = _rows()
        self.assertGreaterEqual(len(rows), 15,
                                'the ledger lost rows — did the table format change?')
        keys = [r[0] for r in rows]
        self.assertEqual(len(keys), len(set(keys)), 'duplicate ledger keys')

    def test_every_anchor_still_exists_in_its_file(self):
        missing = []
        for key, fname, anchor in _rows():
            path = os.path.join(settings.BASE_DIR, *fname.split('/'))
            if not os.path.exists(path):
                missing.append('%s -> file %s not found' % (key, fname))
                continue
            if anchor not in open(path, encoding='utf-8').read():
                missing.append(
                    '%s -> anchor %r no longer in %s. The code that implements '
                    'this semantic changed: re-confirm the meaning and update '
                    'SEMANTICS.md.' % (key, anchor, fname))
        self.assertEqual(missing, [], '\n' + '\n'.join(missing))

    def test_status_values_are_valid(self):
        text = open(LEDGER, encoding='utf-8').read()
        body = text.split('## Ledger', 1)[1].split('##', 1)[0]
        for line in body.splitlines():
            if not line.strip().startswith('|'):
                continue
            cells = [c.strip() for c in line.strip('|').split('|')]
            if len(cells) < 6 or cells[0] in ('Key',) or set(cells[0]) <= {'-', ':', ' '}:
                continue
            self.assertIn(cells[5], {'confirmed', 'pending', 'derived'},
                          'bad status %r for %r' % (cells[5], cells[0]))
