"""
Management command: python manage.py run_alerts

Runs all alert generators in sequence. Intended to be called by a cron job
or Railway's scheduled service (e.g. daily at 08:00 Asia/Dhaka).
"""
from django.core.management.base import BaseCommand

from tracker.alerts import (
    detect_submission_gaps,
    detect_daily_silence,
    generate_below_target_alerts,
    generate_overdue_case_alerts,
)


class Command(BaseCommand):
    help = 'Run all alert generators (below-target, overdue cases, 48-h gaps).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Print alerts without saving.')

    def handle(self, *args, **options):
        dry = options['dry_run']
        prefix = '[DRY RUN] ' if dry else ''

        self.stdout.write(f'{prefix}Generating below-target alerts…')
        below = generate_below_target_alerts(dry_run=dry)
        self.stdout.write(self.style.SUCCESS(f'  {len(below)} alert(s) created'))

        self.stdout.write(f'{prefix}Generating overdue-case alerts…')
        overdue = generate_overdue_case_alerts(dry_run=dry)
        self.stdout.write(self.style.SUCCESS(f'  {len(overdue)} alert(s) created'))

        self.stdout.write(f'{prefix}Detecting 48-hour submission gaps…')
        gaps = detect_submission_gaps(dry_run=dry)
        self.stdout.write(self.style.SUCCESS(f'  {len(gaps)} gap alert(s) created'))

        self.stdout.write(f'{prefix}Detecting missed daily reports…')
        silence = detect_daily_silence(dry_run=dry)
        self.stdout.write(self.style.SUCCESS(f'  {len(silence)} daily-silence alert(s) created'))
