"""
One-off: stamp system_ref on every existing MPDSR case, death notification and
near-miss record, in event-date order so the numbers read chronologically.

    python manage.py backfill_system_refs            # dry-run (prints plan)
    python manage.py backfill_system_refs --apply    # writes refs

No Kobo write-back during backfill (hundreds of PATCHes for records nobody is
editing on the device side is churn without benefit — new records get the
write-back from the live handler).
"""
from django.core.management.base import BaseCommand

from mpdsr.ciprb_models import MPDSRDeathNotification, MaternalNearMissCase
from mpdsr.models import MPDSRCase
from programs.refs import (MPDSR_FORM_CODE, NEAR_MISS_FORM_CODE,
                           SLIP_FORM_CODE, allocate_system_ref)


class Command(BaseCommand):
    help = 'Backfill system_ref on existing MPDSR/notification/near-miss rows.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Actually write refs (default is dry-run).')

    def handle(self, *args, **opts):
        apply = opts['apply']
        plans = [
            ('MPDSR cases',
             MPDSRCase.objects.filter(system_ref__isnull=True, partner='CIPRB')
             .order_by('date_of_death', 'created_at'),
             lambda o: MPDSR_FORM_CODE.get(o.sub_form_type, 'MP')),
            ('Death notifications',
             MPDSRDeathNotification.objects.filter(system_ref__isnull=True)
             .order_by('date_of_death', 'created_at'),
             lambda o: SLIP_FORM_CODE.get(o.slip_variant, 'NS')),
            ('Near-miss cases',
             MaternalNearMissCase.objects.filter(system_ref__isnull=True)
             .order_by('event_date', 'created_at'),
             lambda o: NEAR_MISS_FORM_CODE),
        ]
        for label, qs, code_of in plans:
            rows = list(qs)
            self.stdout.write(f'{label}: {len(rows)} rows without a ref')
            if not apply:
                continue
            done = 0
            for obj in rows:
                if allocate_system_ref(obj, code_of(obj), writeback=False):
                    done += 1
            self.stdout.write(f'  stamped {done}/{len(rows)}')
        if not apply:
            self.stdout.write('Dry-run only — pass --apply to write.')
