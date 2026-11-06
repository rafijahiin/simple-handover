"""Every live CIPRB payload must still pass through its handler without crashing.

The case_hash collision that stranded 90 death records was a handler raising an
IntegrityError on data that already existed in Kobo. This replays every current
CIPRB submission through the real handler (in a rolled-back transaction) and
fails if ANY raises — so that class of regression is caught before it strands
data again.

Hits the live Kobo API; skipped when KOBO_TOKEN is absent. Run with the token —
`railway run python manage.py test programs.test_ciprb_replay` — before trusting
a handler change.
"""
import os
import unittest

from django.db import transaction
from django.test import TestCase

from programs.ciprb_replay import replay_ciprb

KOBO_TOKEN = os.environ.get('KOBO_TOKEN', '')


@unittest.skipUnless(KOBO_TOKEN, 'KOBO_TOKEN not set — run with `railway run` to hit live Kobo')
class CIPRBReplayTest(TestCase):
    def test_no_handler_crashes_on_live_payloads(self):
        # TestCase wraps this in a transaction; replay writes into it and it is
        # rolled back at teardown, so nothing persists. set_rollback makes the
        # intent explicit and covers the case where the whole test DB is real.
        results = replay_ciprb(KOBO_TOKEN)
        transaction.set_rollback(True)

        crashed = []
        for slug, rec in results.items():
            for err in rec['errors']:
                crashed.append('%s [%s]: %s' % (slug, err['id'], err['error']))

        summary = '  '.join(
            '%s ok=%d/%d 4xx=%d' % (slug, rec['ok'], rec['n'], rec['http4xx'])
            for slug, rec in results.items())
        self.assertEqual(crashed, [],
                         'handler crashed on live data:\n' + '\n'.join(crashed)
                         + '\n\nsummary: ' + summary)
