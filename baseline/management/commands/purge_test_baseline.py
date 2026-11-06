"""Delete pre-launch TEST/pilot baseline submissions, keeping the demo set.

Baseline submissions that arrived from real KoboToolbox form-testing (before
data collection formally started) live in the Django DB with a real Kobo id —
NOT the seed's `DEMO-BL-` prefix — so `seed_baseline_demo --wipe` never removes
them. They surface on the monitor as an 'Unknown' enumerator (no in-form name)
and inflate the totals. This command removes exactly those non-demo rows.

Deleting the submissions inside KoboToolbox does NOT remove them here: the
dashboard reads the Django DB, populated by webhook at submission time, and Kobo
sends no delete webhook. This is the only way to clear them from the dashboard.

Prod DB is only reachable from inside Railway, so this runs via the Dockerfile
boot gate `PURGE_TEST_BASELINE=1` (set → redeploy → verify → unset), like
SEED_BASELINE_DEMO. Dry-run by default; pass --commit to actually delete.
"""
from django.core.management.base import BaseCommand

from baseline.models import BaselineResponse
from submissions.models import FormType, KoboSubmission

PREFIX = 'DEMO-BL-'


class Command(BaseCommand):
    help = 'Delete non-demo (pre-launch test/pilot) baseline submissions; keeps the DEMO-BL- demo set.'

    def add_arguments(self, parser):
        parser.add_argument('--commit', action='store_true',
                            help='Actually delete (default is a dry run).')

    def handle(self, *args, **opts):
        subs = (KoboSubmission.objects
                .filter(form_type=FormType.BASELINE)
                .exclude(kobo_id__startswith=PREFIX))
        n = subs.count()
        kept = KoboSubmission.objects.filter(
            form_type=FormType.BASELINE, kobo_id__startswith=PREFIX).count()
        self.stdout.write(f'Non-demo baseline submissions to purge: {n} (keeping {kept} demo rows)')
        if n:
            sample = list(subs.values_list('kobo_id', flat=True)[:5])
            self.stdout.write(f'  sample ids: {sample}')
        if not opts['commit']:
            self.stdout.write('Dry run — pass --commit to delete.')
            return
        resp_deleted, _ = BaselineResponse.objects.filter(submission__in=subs).delete()
        sub_deleted, _ = subs.delete()
        self.stdout.write(f'Deleted {sub_deleted} submission(s) + {resp_deleted} response row(s). '
                          f'{kept} demo rows preserved.')
