"""Seed CIPRB ServiceCenter rows from Sayeed's MPDSR facility list.

The MPDSRFacilityCount table (ingested from Sayeed's Excel) holds 65 named
facilities across 7 districts. Each one is a real CIPRB MPDSR site. This
command creates matching ServiceCenter rows so the Programme Health Flag
'X of N centres submitted today' calculation has real denominators.

Idempotent: existing centres with the same code are skipped.
"""
import re
from django.core.management.base import BaseCommand
from programs.models.center import ServiceCenter
from mpdsr.models import MPDSRFacilityCount


def code_from(district: str, facility: str) -> str:
    """Build a stable short code from district + facility name."""
    d = re.sub(r'[^A-Z0-9]', '', district.upper())[:4]
    f = re.sub(r'[^A-Z0-9]', '', facility.upper())[:8]
    return f'{d}-{f}'[:20]


class Command(BaseCommand):
    help = 'Seed CIPRB ServiceCenter rows from Sayeed\'s MPDSRFacilityCount data.'

    def handle(self, *args, **options):
        created = 0
        skipped = 0
        for fac in MPDSRFacilityCount.objects.all():
            code = code_from(fac.district, fac.facility_name)
            if ServiceCenter.objects.filter(code=code).exists():
                skipped += 1
                continue
            # Pick a reasonable centre_type — CIPRB facilities are mostly DH/UHC,
            # closest match in our enum is SUB_DIC (district health complex) or
            # MOBILE (UHC). Default to SUB_DIC; admins can fix later.
            ServiceCenter.objects.create(
                organisation='CIPRB',
                name=fac.facility_name[:200],
                code=code,
                center_type=ServiceCenter.SUB_DIC,
                district=fac.district,
                upazila='',
                is_active=True,
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Created {created} CIPRB centres, skipped {skipped} existing.'
        ))
