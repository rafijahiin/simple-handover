"""
python manage.py generate_monthly_hub [--year Y --month M] [--regenerate] [--no-narrative]

Generate the 10-piece monthly Reporting Hub set (per-org report + infographic;
overall report / infographic / deck / web report) from live approved data.

Defaults to the PREVIOUS calendar month, so a cron on the 1st produces last
month's finished set. Idempotent — re-runs skip pieces that already exist
(use --regenerate to rebuild them).

CRON: run on a SEPARATE Railway service (not the gunicorn web service — Chromium
rendering is heavy) on the 1st of each month at 02:00 UTC (08:00 Asia/Dhaka):

    0 2 1 * *

start command:

    python manage.py migrate --noinput && python manage.py generate_monthly_hub
"""
from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from reports.generators.monthly import generate_monthly_set


class Command(BaseCommand):
    help = 'Generate the monthly Reporting Hub set (10 branded pieces) from live data.'

    def add_arguments(self, parser):
        today = date.today()
        py, pm = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        parser.add_argument('--year', type=int, default=py)
        parser.add_argument('--month', type=int, default=pm)
        parser.add_argument('--regenerate', action='store_true',
                            help='Delete + rebuild pieces that already exist for the month.')
        parser.add_argument('--no-narrative', action='store_true',
                            help='Skip the AI narrative (deterministic / offline-safe).')

    def handle(self, *args, **o):
        User = get_user_model()
        try:
            user = (User.objects.filter(role='developer').first()
                    or User.objects.filter(is_superuser=True).first())
        except Exception:                                          # noqa: BLE001
            user = None

        self.stdout.write(
            f'Generating monthly hub set for {o["year"]}-{o["month"]:02d} '
            f'(regenerate={o["regenerate"]})...'
        )
        res = generate_monthly_set(
            o['year'], o['month'], system_user=user,
            include_narrative=not o['no_narrative'], regenerate=o['regenerate'],
            log=self.stdout.write,
        )
        style = self.style.SUCCESS if res['failed'] == 0 else self.style.WARNING
        self.stdout.write(style(
            f'Done {res["period"]}: {res["created"]} created, '
            f'{res["skipped"]} skipped, {res["failed"]} failed.'
        ))
