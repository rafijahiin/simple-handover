"""Backfill KoboSubmission.centre_code from raw_data for pre-existing rows.

Run once after the centre_code denormalisation lands. Idempotent: rows that
already have a centre_code are skipped.
"""
from django.core.management.base import BaseCommand
from submissions.models import KoboSubmission


class Command(BaseCommand):
    help = 'Backfill KoboSubmission.centre_code from raw_data payloads.'

    def handle(self, *args, **options):
        updated = 0
        scanned = 0
        for sub in KoboSubmission.objects.filter(centre_code='').iterator():
            scanned += 1
            payload = sub.raw_data or {}
            code = (
                payload.get('center_code')
                or payload.get('centre_code')
                or payload.get('site_code')
                or ''
            )
            code = (code or '').strip()[:40]
            if code:
                sub.centre_code = code
                sub.save(update_fields=['centre_code'])
                updated += 1
        self.stdout.write(self.style.SUCCESS(
            f'Scanned {scanned} rows without centre_code, backfilled {updated}.'
        ))
