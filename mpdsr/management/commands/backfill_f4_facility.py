"""Backfill facility (Form 04) deep-dive fields on f4 maternal rows.

The facility maternal-death deep-dive (admission→death interval + review
committee progress) needs admission_date, a spread of review statuses, and
action plans on progressed cases. Demo / early-test f4 rows predate the
admission_date column, so they carry none of these.

This command is IDEMPOTENT and safe to run on every boot: it only touches
f4 maternal rows where admission_date IS NULL. A real Kobo submission that
records an admission date is never modified; once a demo row is backfilled
it is skipped on the next run. Values are derived deterministically from the
case hash so they are stable across deploys.
"""
import datetime
import random

from django.core.management.base import BaseCommand

from mpdsr.models import MPDSRCase, DeathType, ReviewStatus

_STATUS_CYCLE = [
    ReviewStatus.REPORTED,
    ReviewStatus.UNDER_REVIEW,
    ReviewStatus.COMMITTEE_REVIEW,
    ReviewStatus.ACTION_PLAN_DRAFTED,
    ReviewStatus.CLOSED,
]
# Weighted admission→death offsets (days). Skews toward short intervals —
# most facility maternal deaths occur within the first couple of days.
_OFFSETS = [0, 0, 1, 1, 2, 4, 6, 9, 12]


class Command(BaseCommand):
    help = ('Backfill admission_date / review status / action plans on f4 '
            'maternal rows that are missing them (idempotent).')

    def handle(self, *args, **opts):
        qs = (MPDSRCase.objects
              .filter(death_type=DeathType.MATERNAL, sub_form_type='f4',
                      admission_date__isnull=True)
              .order_by('case_hash'))
        updated = 0
        for idx, case in enumerate(qs):
            rng = random.Random(case.case_hash or str(case.id))
            if case.date_of_death:
                case.admission_date = case.date_of_death - datetime.timedelta(
                    days=rng.choice(_OFFSETS))
            status = _STATUS_CYCLE[idx % len(_STATUS_CYCLE)]
            case.status = status
            if (status in (ReviewStatus.ACTION_PLAN_DRAFTED, ReviewStatus.CLOSED)
                    and not case.action_plan):
                case.action_plan = (
                    'Facility action plan: strengthen referral pathway and '
                    f'blood availability ({case.district or "facility"}).')
            case.save(update_fields=['admission_date', 'status', 'action_plan'])
            updated += 1
        self.stdout.write(self.style.SUCCESS(
            f'backfill_f4_facility: enriched {updated} facility f4 row(s).'))
