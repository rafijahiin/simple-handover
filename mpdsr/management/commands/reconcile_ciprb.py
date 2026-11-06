"""Reconcile every CIPRB Kobo form against the app and store a snapshot.

Runs each form's live submissions through the real handler inside a rolled-back
savepoint and records how many rows the handlers had to create — i.e. how many
Kobo submissions are MISSING from the app right now (see mpdsr/reconcile.py).
The dashboard reads the stored snapshot via /api/mpdsr/reconciliation/.

    railway run python manage.py reconcile_ciprb

Must run where the real DB is reachable (Railway) — on an empty/local DB every
payload looks stranded. Exit code is non-zero if any form shows drift or crashes.
"""
import os
import sys

from django.core.management.base import BaseCommand, CommandError

from mpdsr.reconcile import run_and_store


class Command(BaseCommand):
    help = ('Reconcile CIPRB + PHD + Bandhu Kobo forms vs app rows; store a snapshot for /ciprb. Partner forms are discovered from their webhooks.')

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=None,
                            help='Max submissions per form (for a quick check).')

    def handle(self, *args, **opts):
        token = os.environ.get('KOBO_TOKEN', '')
        if not token:
            raise CommandError('KOBO_TOKEN is not set — run via `railway run`.')

        snap = run_and_store(token, limit=opts.get('limit'))
        data = snap.data
        drift = False
        for r in data['forms']:
            if 'error' in r:
                self.stdout.write(self.style.WARNING('  %-38s %s' % (r['slug'], r['error'])))
                continue
            bad = (r['stranded'] > 0) or (r['crashes'] > 0) or not r.get('hook_active')
            drift = drift or (r['stranded'] > 0) or (r['crashes'] > 0)
            line = ('  %-38s kobo=%-4d app=%-4d stranded=%-3d crashes=%-2d hook=%s'
                    % (r['slug'], r['kobo_count'], r['app_rows'], r['stranded'],
                       r['crashes'], 'up' if r.get('hook_active') else 'DOWN'))
            self.stdout.write((self.style.ERROR if bad else self.style.SUCCESS)(line))
            for c in r.get('crash_detail', []):
                self.stdout.write(self.style.ERROR('      crash %s: %s'
                                                   % (c['id'], c['error'])))

        self.stdout.write('')
        self.stdout.write('  total stranded (missing from app): %d' % data['total_stranded'])
        self.stdout.write('  total handler crashes: %d' % data['total_crashes'])
        self.stdout.write('  snapshot saved @ %s' % snap.run_at.isoformat())
        if drift:
            self.stdout.write(self.style.ERROR('\nDRIFT: some Kobo data is not in the app.'))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS('\nAll CIPRB forms reconciled - no drift.'))
