"""Backfill the F-01 Wellness Logbook rows created before the 2026-07 MIS rewire.

Two things per existing WellnessLogbookEntry:
  1. populate the new service-flag / count columns from raw_payload (so the
     Bandhu service indicators can read them), and
  2. set client_id_norm — the DD-NNNN form — repairing the bare-serial IDs
     ('0002' → '08-0002') so each service links to its Mother List registration.

Non-destructive: the as-submitted client_id and raw_payload are untouched.
Dry-run by default; pass --commit to write. Runs on prod via the Dockerfile
env-gate (BACKFILL_WELLNESS_LOGBOOK=1), since the prod DB is internal-only.
"""
from django.core.management.base import BaseCommand

from programs.models import WellnessLogbookEntry
from programs.bandhu_handlers import _log_service_fields, _norm_client_id


class Command(BaseCommand):
    help = 'Populate service-flag columns + normalised client_id on existing F-01 logbook rows.'

    def add_arguments(self, parser):
        parser.add_argument('--commit', action='store_true',
                            help='Write changes (otherwise dry-run).')

    def handle(self, *args, **opts):
        commit = opts['commit']
        qs = WellnessLogbookEntry.objects.select_related('center')
        total = qs.count()
        changed = repaired = skipped = 0
        for e in qs.iterator():
            try:
                payload = e.raw_payload or {}
                fields = _log_service_fields(payload)
                norm = _norm_client_id(e.client_id, e.center)
                dirty = False
                for k, v in fields.items():
                    if getattr(e, k) != v:
                        setattr(e, k, v)
                        dirty = True
                if e.client_id_norm != norm:
                    if norm and norm != (e.client_id or '').strip().upper():
                        repaired += 1
                    e.client_id_norm = norm
                    dirty = True
                if dirty:
                    changed += 1
                    if commit:
                        e.save(update_fields=list(fields.keys()) + ['client_id_norm'])
            except Exception as exc:  # one bad legacy row must not abort the whole backfill
                skipped += 1
                self.stderr.write(f'skip logbook row {e.pk}: {exc}')
        mode = 'COMMITTED' if commit else 'DRY-RUN (no writes)'
        self.stdout.write(self.style.SUCCESS(
            f'{mode}: {changed}/{total} logbook rows updated; '
            f'{repaired} client IDs normalised; {skipped} skipped.'))
