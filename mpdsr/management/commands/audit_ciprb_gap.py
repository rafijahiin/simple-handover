"""Name every Kobo submission that has no row in the app, with its date.

`reconcile_ciprb` answers "is anything missing since go-live" and is what the
dashboard strip reads. It deliberately ignores submissions made before
28 June 2026, because those are the training and pilot entries that were
flushed at go-live.

That is the right default, but it cannot answer the question CIPRB actually
asks, which is: "KoboToolbox shows 56 for CIPRB-2 and the dashboard shows 49,
so name the 7." This command names them. It replays every submission
individually, with NO cutoff, and reports each one the app does not already
hold, dated and classified either side of go-live. The point is to replace
"they are probably pilot data" with a list.

    railway run python manage.py audit_ciprb_gap
    railway run python manage.py audit_ciprb_gap --form ciprb_mpdsr_community_maternal_v1
    railway run python manage.py audit_ciprb_gap --json > gap.json

Read-only: every replay runs inside a savepoint that is rolled back, and the
whole command runs inside a transaction that is rolled back at the end, so
nothing is written even if a handler tries to.

Must run where the real DB is reachable (Railway). On an empty or local DB
every submission looks missing, which tells you nothing.
"""
import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mpdsr.reconcile import GO_LIVE_CUTOFF, audit_ciprb_gap


class Command(BaseCommand):
    help = 'List the Kobo submissions missing from the app, dated, with a pre/post go-live split.'

    def add_arguments(self, parser):
        parser.add_argument('--form', action='append', dest='forms', default=None,
                            help='Restrict to one or more form slugs. Repeatable.')
        parser.add_argument('--limit', type=int, default=None,
                            help='Max submissions per form (for a quick check).')
        parser.add_argument('--json', action='store_true',
                            help='Emit raw JSON instead of the readable table.')

    def handle(self, *args, **opts):
        token = os.environ.get('KOBO_TOKEN', '')
        if not token:
            raise CommandError('KOBO_TOKEN is not set. Run this via `railway run`.')

        # Outer transaction rolled back at the end: belt and braces on top of the
        # per-submission savepoints, so an audit can never mutate production.
        results = None
        sp = transaction.savepoint() if transaction.get_connection().in_atomic_block else None
        try:
            with transaction.atomic():
                results = audit_ciprb_gap(token, slugs=opts.get('forms'),
                                          limit=opts.get('limit'))
                transaction.set_rollback(True)
        except Exception:
            if sp:
                transaction.savepoint_rollback(sp)
            raise

        if opts.get('json'):
            self.stdout.write(json.dumps(results, indent=2, default=str))
            return

        self.stdout.write('')
        self.stdout.write('CIPRB Kobo-vs-app gap audit')
        self.stdout.write('Go-live cutoff: %s (earlier submissions are pilot data '
                          'flushed at go-live)' % GO_LIVE_CUTOFF)
        self.stdout.write('=' * 78)

        tot_missing = tot_pre = tot_live = 0
        for r in results:
            if 'error' in r:
                self.stdout.write(self.style.WARNING(
                    '%-38s %s' % (r['slug'], r['error'])))
                continue
            tot_missing += r['missing_total']
            tot_pre += r['missing_pre_go_live']
            tot_live += r['missing_live']

            headline = ('%-38s kobo %4d | app %4d | missing %3d '
                        '(pilot %3d, LIVE %3d)'
                        % (r['slug'], r['kobo_count'], r['app_rows'],
                           r['missing_total'], r['missing_pre_go_live'],
                           r['missing_live']))
            style = self.style.ERROR if r['missing_live'] else self.style.SUCCESS
            self.stdout.write(style(headline))

            for m in r['missing']:
                tag = 'pilot' if m['pre_go_live'] else 'LIVE '
                self.stdout.write('      %s  %s  id=%-10s %s'
                                  % (tag, m['date'] or '(no date)',
                                     m['id'], m['district']))
            for c in r['crashes']:
                self.stdout.write(self.style.ERROR(
                    '      CRASH %s id=%s  %s' % (c['date'], c['id'], c['error'])))

        self.stdout.write('=' * 78)
        self.stdout.write('Missing in total: %d  (pilot %d, live %d)'
                          % (tot_missing, tot_pre, tot_live))
        if tot_live:
            self.stdout.write(self.style.ERROR(
                '%d submission(s) made AFTER go-live are missing from the app. '
                'These are real data loss and need recovery.' % tot_live))
        else:
            self.stdout.write(self.style.SUCCESS(
                'Every missing submission predates go-live. Nothing has been '
                'lost since the system went live.'))
        self.stdout.write(
            'Note: each submission is tested independently, so a duplicate pair '
            'mapping to one absent row is listed twice. Treat the count as an '
            'upper bound on distinct missing rows.')
