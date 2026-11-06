"""
Management command: python manage.py seed_targets [--year Y] [--month M] [--force]

Seeds MonthlyTarget records for all programs form types across both organisations.
Placeholder targets of 20 per form type — super admins should adjust via the UI.
Run once per month or use --force to overwrite existing targets.
"""
import datetime

from django.core.management.base import BaseCommand

from tracker.models import MonthlyTarget
from tracker.programs_query import PROGRAMS_REGISTRY, LEGACY_REGISTRY

# Default placeholder targets (super admins adjust via UI)
DEFAULT_TARGETS: dict[str, int] = {
    'clinic_visit':       30,
    'hiv_sti_test':       20,
    'adr_record':         5,
    'autoclave_log':      4,
    'antenatal_card':     20,
    'htc_counselling':    10,
    'individual_counsel': 10,
    'mh_screening':       8,
    'gbv_case':           5,
    'outreach_session':   15,
    'group_education':    10,
    'referral':           8,
    'hygiene_kit':        5,
    'training_event':     2,
    'coord_meeting':      2,
    'mobile_camp':        1,
    # Legacy
    'mpdsr':              5,
    'fistula':            10,
    'activity':           20,
    'baseline':           10,
}

ORGS = ['PHD', 'Bandhu']


class Command(BaseCommand):
    help = 'Seed default MonthlyTarget records for all form types.'

    def add_arguments(self, parser):
        today = datetime.date.today()
        parser.add_argument('--year',  type=int, default=today.year)
        parser.add_argument('--month', type=int, default=today.month)
        parser.add_argument('--force', action='store_true',
                            help='Overwrite existing targets.')

    def handle(self, *args, **options):
        year  = options['year']
        month = options['month']
        force = options['force']
        created = updated = skipped = 0

        all_types = dict(
            list(PROGRAMS_REGISTRY.items()) +
            [(k, (None, v[0], v[1], v[2])) for k, v in LEGACY_REGISTRY.items()]
        )

        for form_type_key in all_types:
            default_target = DEFAULT_TARGETS.get(form_type_key, 10)
            for org in ORGS:
                existing = MonthlyTarget.objects.filter(
                    partner=org, form_type=form_type_key,
                    year=year, month=month,
                ).first()

                if existing:
                    if force:
                        existing.target = default_target
                        existing.save(update_fields=['target'])
                        updated += 1
                    else:
                        skipped += 1
                else:
                    MonthlyTarget.objects.create(
                        partner=org,
                        form_type=form_type_key,
                        year=year,
                        month=month,
                        target=default_target,
                    )
                    created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done — created: {created}, updated: {updated}, skipped: {skipped}'
        ))
        self.stdout.write(
            f'Period: {year}-{month:02d}  |  '
            f'Adjust targets at /tracker in the dashboard.'
        )
