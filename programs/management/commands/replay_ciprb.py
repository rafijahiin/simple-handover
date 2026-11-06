"""Replay live CIPRB Kobo payloads through the real handlers, then roll back.

Prod-runnable form of the replay guard (programs/test_ciprb_replay mirrors it in
the test suite). Runs every current CIPRB submission through its handler inside a
transaction that is ALWAYS rolled back — nothing persists — and reports any that
crash. Catches the case_hash-collision class of regression against real data.

    railway run python manage.py replay_ciprb
    railway run python manage.py replay_ciprb --slug ciprb_mpdsr_community_maternal_v1

Exit code is non-zero if any handler crashed, so it can gate a check.
"""
import os
import sys

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from programs.ciprb_replay import CIPRB_SLUG_TO_UID, replay_ciprb


class Command(BaseCommand):
    help = 'Replay live CIPRB Kobo payloads through the handlers (rolled back).'

    def add_arguments(self, parser):
        parser.add_argument('--slug', action='append', dest='slugs',
                            help='Limit to these slug(s); repeatable.')
        parser.add_argument('--limit', type=int, default=None,
                            help='Max submissions per form.')

    def handle(self, *args, **opts):
        token = os.environ.get('KOBO_TOKEN', '')
        if not token:
            raise CommandError('KOBO_TOKEN is not set — run via `railway run`.')
        slugs = opts.get('slugs') or None
        if slugs:
            bad = [s for s in slugs if s not in CIPRB_SLUG_TO_UID]
            if bad:
                raise CommandError('unknown slug(s): %s' % bad)

        # Everything runs inside one transaction that is unconditionally rolled
        # back — the replay is a dry run, it must never persist.
        crashed = []
        with transaction.atomic():
            results = replay_ciprb(token, slugs=slugs, limit=opts.get('limit'))
            transaction.set_rollback(True)

        for slug, rec in results.items():
            line = '  %-38s n=%-4d ok=%-4d 4xx=%-3d crashes=%d' % (
                slug, rec['n'], rec['ok'], rec['http4xx'], len(rec['errors']))
            style = self.style.ERROR if rec['errors'] else self.style.SUCCESS
            self.stdout.write(style(line))
            for err in rec['errors']:
                crashed.append('%s [%s]: %s' % (slug, err['id'], err['error']))
                self.stdout.write(self.style.ERROR('      CRASH %s: %s'
                                                   % (err['id'], err['error'])))

        if crashed:
            self.stdout.write(self.style.ERROR(
                '\n%d handler crash(es) on live data — a handler would 500 and '
                'strand these submissions.' % len(crashed)))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS(
            '\nAll live CIPRB payloads replayed cleanly (no handler crashes).'))
