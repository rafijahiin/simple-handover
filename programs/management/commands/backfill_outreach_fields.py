"""Repair Bandhu F-04 Daily Outreach rows created BEFORE the Kobo group-key
flattener existed (commit b987977).

Those early submissions were processed with grouped keys ('grp_outreach/or_condom')
that the handler could not read, so condoms / lubricants / awareness / IEC / referral
counts all saved as 0 — every approval card then read an identical, empty
"reached 0 contacts and distributed 0 condoms". Because Kobo re-delivery is
idempotent (_already_exists), later redeploys never re-mapped them.

This re-reads each OutreachSession.raw_payload, FLATTENS it (so both the old
grouped keys and the new flat aliases resolve), and repopulates the count columns
via the SAME _outreach_service_fields mapping the live handler uses. Non-destructive:
raw_payload is untouched. Dry-run by default; --commit writes. Runs on prod via the
Dockerfile boot line, since the prod DB is internal-only.
"""
from django.core.management.base import BaseCommand

from programs.models import OutreachSession
from programs.bandhu_handlers import _outreach_service_fields
from programs.webhook import _flatten_group_keys


class Command(BaseCommand):
    help = 'Repopulate Bandhu OutreachSession count columns from raw_payload.'

    def add_arguments(self, parser):
        parser.add_argument('--commit', action='store_true',
                            help='Write changes (otherwise dry-run).')

    def handle(self, *args, **opts):
        commit = opts['commit']
        qs = OutreachSession.objects.filter(organisation='Bandhu')
        total = qs.count()
        changed = empty = skipped = 0
        for o in qs.iterator():
            try:
                payload = o.raw_payload or {}
                if not payload:
                    empty += 1
                    continue
                fields = _outreach_service_fields(_flatten_group_keys(payload))
                dirty = False
                for k, v in fields.items():
                    if getattr(o, k) != v:
                        setattr(o, k, v)
                        dirty = True
                if dirty:
                    changed += 1
                    if commit:
                        o.save(update_fields=list(fields.keys()))
            except Exception as exc:  # one bad legacy row must not abort the backfill
                skipped += 1
                self.stderr.write(f'skip outreach row {o.pk}: {exc}')
        mode = 'COMMITTED' if commit else 'DRY-RUN (no writes)'
        self.stdout.write(self.style.SUCCESS(
            f'{mode}: {changed}/{total} outreach rows updated; '
            f'{empty} had empty raw_payload; {skipped} skipped.'))
