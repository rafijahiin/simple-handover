"""One-time backlog approval for the F-01 Wellness Logbook.

Before the 2026-07 MIS rewire the logbook fed no indicator, so 450+ real Bandhu
service rows sat PENDING. Now that the logbook IS the counted service source,
this approves that pre-rewire backlog so the numbers show on the dashboard.

BOUNDED by a fixed cutoff (created_at < CUTOFF) so it is SAFE to run on every
boot: it only ever touches the old backlog, never future submissions — those keep
the normal two-stage (manager -> UNFPA) review.
"""
from datetime import datetime, timezone

from django.core.management.base import BaseCommand

from programs.models import WellnessLogbookEntry

# Everything submitted before this instant is the pre-rewire backlog.
CUTOFF = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


class Command(BaseCommand):
    help = 'Approve the pre-rewire PENDING Bandhu F-01 logbook backlog (created before CUTOFF).'

    def handle(self, *args, **options):
        qs = WellnessLogbookEntry.objects.filter(
            organisation='Bandhu',
            approval_status__in=[
                WellnessLogbookEntry.PENDING,
                WellnessLogbookEntry.MANAGER_APPROVED,  # also promote stage-1 backlog
            ],
            created_at__lt=CUTOFF,
        )
        n = qs.update(approval_status=WellnessLogbookEntry.APPROVED)
        self.stdout.write(self.style.SUCCESS(
            f'Approved {n} pre-rewire Bandhu logbook backlog row(s).'))
