"""Backfill KoboSubmission.worker_name where it is blank.

Older webhook submissions (and the CIPRB surveillance forms that have no
explicit collector-name question) left worker_name empty, so the manager
approval queue showed "Submitted by: Unknown". This command fills the gap:

  1. Prefer any identity carried in the payload — Kobo's `_submitted_by`
     username, or a collector/enumerator name field.
  2. Otherwise fall back to a role label based on the form type, so the
     surveillance forms read as the cadre that actually files them rather
     than "Unknown".

Idempotent: only rows with a blank worker_name are touched, so it is safe
to run on every deploy.
"""
from django.core.management.base import BaseCommand

from submissions.models import KoboSubmission, FormType


# Who actually files each CIPRB-owned form, used only when the payload
# carries no submitter identity at all (e.g. legacy test submissions).
ROLE_DEFAULTS = {
    FormType.MPDSR:               'CIPRB MPDSR Reviewer',
    FormType.MPDSR_RESPONSE_PLAN: 'CIPRB MPDSR Focal',
    FormType.FISTULA:             'CIPRB Fistula Team',
    FormType.FISTULA_STAGED:      'CIPRB Fistula Surgeon',
    FormType.BASELINE:            'CIPRB Survey Enumerator',
    FormType.ACTIVITY:            'Field Worker',
}


class Command(BaseCommand):
    help = 'Fill blank KoboSubmission.worker_name from payload identity or a role default.'

    def handle(self, *args, **opts):
        qs = KoboSubmission.objects.filter(worker_name='')
        updated = 0
        for sub in qs.iterator():
            rd = sub.raw_data or {}
            name = (
                rd.get('collector_name')
                or rd.get('worker_name')
                or rd.get('enumerator_name')
                or rd.get('_submitted_by')
                or ROLE_DEFAULTS.get(sub.form_type, 'Field worker')
            )
            sub.worker_name = str(name)[:200]
            sub.save(update_fields=['worker_name'])
            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Backfilled worker_name on {updated} submission(s).'
        ))
