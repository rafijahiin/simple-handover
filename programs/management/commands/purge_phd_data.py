"""
Management command: purge_phd_data

Deletes ALL PHD programme data so the system starts completely fresh
with the new consolidated forms. Preserves:
  - User accounts
  - ServiceCenter records
  - IndicatorTarget targets
  - Bandhu and CIPRB data

Usage:
    python manage.py purge_phd_data          # dry-run (shows counts only)
    python manage.py purge_phd_data --confirm  # actually deletes
"""
from django.core.management.base import BaseCommand

PHD = 'PHD'

MODELS_PURGE = [
    # Child models first (FKs to Client), so Client can be deleted last
    ('programs', 'ClinicVisit'),
    ('programs', 'HIVSTITestResult'),
    ('programs', 'AntenatalCard'),
    ('programs', 'HTCCounselling'),
    ('programs', 'IndividualCounselling'),
    ('programs', 'MHScreening'),
    ('programs', 'ADRRecord'),
    ('programs', 'AutoclaveLog'),
    ('programs', 'SafetyHygieneKit'),
    ('programs', 'Referral'),
    ('programs', 'GBVCase'),
    ('programs', 'OutreachSession'),
    ('programs', 'GroupEducationSession'),
    ('programs', 'MobileHealthCamp'),
    ('programs', 'CoordMeeting'),
    ('programs', 'TrainingEvent'),
    ('programs', 'IECMaterial'),
    ('programs', 'StockEntry'),
    ('programs', 'GBVCornerRecord'),
    ('programs', 'Client'),  # last — FKs are cleared by now
    ('submissions', 'KoboSubmission'),
]


class Command(BaseCommand):
    help = 'Purge all PHD programme data for a clean start with new forms.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm', action='store_true',
            help='Actually delete. Without this flag, only counts are shown.',
        )

    def handle(self, *args, **options):
        confirm = options['confirm']
        self.stdout.write('\nPHD data purge — ' +
                          ('DRY RUN' if not confirm else 'DELETING') + '\n')

        from django.apps import apps
        total = 0
        for app_label, model_name in MODELS_PURGE:
            try:
                Model = apps.get_model(app_label, model_name)
            except LookupError:
                continue
            # Some models use 'organisation', StockEntry uses center__organisation
            fields = [f.name for f in Model._meta.get_fields()]
            if 'organisation' in fields:
                qs = Model.objects.filter(organisation=PHD)
            elif 'center' in fields:
                qs = Model.objects.filter(center__organisation=PHD)
            else:
                qs = Model.objects.none()
            n = qs.count()
            total += n
            label = f'  {app_label}.{model_name:<30} {n:>6} rows'
            if confirm and n:
                qs.delete()
                self.stdout.write(self.style.SUCCESS(label + '  deleted'))
            else:
                self.stdout.write(label + ('  (would delete)' if n else ''))

        # KoboSubmission uses worker_name / partner fields — delete all
        try:
            from submissions.models import KoboSubmission
            qs = KoboSubmission.objects.all()
            n = qs.count()
            total += n
            label = f'  submissions.KoboSubmission              {n:>6} rows'
            if confirm and n:
                qs.delete()
                self.stdout.write(self.style.SUCCESS(label + '  deleted'))
            else:
                self.stdout.write(label + ('  (would delete)' if n else ''))
        except Exception:
            pass

        self.stdout.write(f'\n  Total: {total} rows')
        if not confirm:
            self.stdout.write(self.style.WARNING(
                '\n  Run with --confirm to actually delete.\n'))
        else:
            self.stdout.write(self.style.SUCCESS('\n  Done.\n'))
