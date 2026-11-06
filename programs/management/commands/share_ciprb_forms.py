"""
Share every CIPRB Kobo form with a field account (default: ciprb_field) so the
account can download the blank forms in KoboCollect and submit, but cannot edit
or manage anything.

Why: a KoboCollect "Configure via QR" account only sees forms that are shared
with it. The CIPRB field account saw no forms (not even Safe Surgery) because
nothing was shared to it yet.

Permissions granted (submit + view only):
  view_asset        - see and download the blank form in KoboCollect
  add_submissions   - submit data
  view_submissions  - view the data it is given access to
NOT granted: change_asset / manage_asset / change_submissions /
delete_submissions / validate_submissions - so the field account can never
alter the forms or other people's data.

Runs against Kobo only (reachable via `railway run`):
  railway run python manage.py share_ciprb_forms
  railway run python manage.py share_ciprb_forms --to someone_else
"""
import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from programs.kobo_assets import AssetNotFound, resolve_asset_uid

KOBO_BASE = 'https://kf.kobotoolbox.org/api/v2'
TIMEOUT = 60

CIPRB_FORMS = [
    ('ciprb_fistula_questions_v1',        'CIPRB 1 — Fistula Question Bank'),
    ('ciprb_fistula_campaign_v1',         'CIPRB — Fistula Campaign (Daily CHW Activity)'),
    ('ciprb_mpdsr_community_maternal_v1',  'CIPRB 2 — MPDSR Form 01 (Community Maternal Death)'),
    ('ciprb_mpdsr_community_neonatal_v1',  'CIPRB 3 — MPDSR Form 02 (Community Neonatal Death)'),
    ('ciprb_mpdsr_facility_maternal_v1',   'CIPRB 4 — MPDSR Form 04 (Facility Maternal Death)'),
    ('ciprb_mpdsr_facility_neonatal_v1',   'CIPRB 5 — MPDSR Form 05 (Facility Neonatal Death)'),
    ('ciprb_social_autopsy_v1',            'CIPRB 6 — Social Autopsy (Maternal Death)'),
    ('ciprb_notification_slip_01_v1',      'CIPRB 7 — Death Notification Slip 01'),
    ('ciprb_notification_slip_02_v1',      'CIPRB 8 — Death Notification Slip 02'),
    ('ciprb_near_miss_v1',                 'CIPRB 9 — Maternal Near Miss audit'),
    ('ciprb_mpdsr_response_plan_v1',       'CIPRB 10 — MPDSR Response Plan'),
    ('ciprb_safe_surgery_v1',              'CIPRB 11 — Safe Surgery Checklist'),
]

GRANT = ['view_asset', 'add_submissions', 'view_submissions']


def _token():
    return (getattr(settings, 'KOBO_API_TOKEN', '')
            or __import__('os').environ.get('KOBO_TOKEN', '')).strip()


class Command(BaseCommand):
    help = 'Share all CIPRB forms with a field account (submit + view only).'

    def add_arguments(self, parser):
        parser.add_argument('--to', default='ciprb_field',
                            help='Kobo username to share with (default ciprb_field).')

    def handle(self, *args, **opts):
        token = _token()
        if not token:
            self.stderr.write('KOBO_TOKEN not set; run under `railway run`.')
            return
        user = opts['to']
        headers = {'Authorization': 'Token ' + token}
        user_url = '%s/users/%s/' % (KOBO_BASE, user)
        perm_urls = {p: '%s/permissions/%s/' % (KOBO_BASE, p) for p in GRANT}

        self.stdout.write(self.style.MIGRATE_HEADING(
            'Sharing %d CIPRB forms with %s (submit + view only)\n'
            % (len(CIPRB_FORMS), user)))

        for form_id, title in CIPRB_FORMS:
            try:
                uid = resolve_asset_uid(form_id, title, token, stdout=self.stdout)
            except AssetNotFound as exc:
                self.stdout.write(self.style.ERROR('  SKIP %-34s %s' % (form_id, exc)))
                continue
            # existing assignments for this user, so we do not duplicate
            existing = set()
            list_url = '%s/assets/%s/permission-assignments/' % (KOBO_BASE, uid)
            lr = requests.get(list_url, headers=headers, timeout=TIMEOUT)
            if lr.ok:
                for a in lr.json():
                    if str(a.get('user', '')).rstrip('/').endswith('/' + user):
                        existing.add(str(a.get('permission', '')).rstrip('/').rsplit('/', 1)[-1])
            done = []
            for perm, purl in perm_urls.items():
                if perm in existing:
                    done.append(perm + '(had)')
                    continue
                r = requests.post(list_url, headers=headers, timeout=TIMEOUT,
                                  json={'user': user_url, 'permission': purl})
                if r.status_code in (200, 201):
                    done.append(perm)
                else:
                    done.append('%s(FAIL %s)' % (perm, r.status_code))
            self.stdout.write('  %-34s %s  ->  %s'
                              % (form_id, uid, ', '.join(done)))

        self.stdout.write(self.style.SUCCESS(
            '\nDone. In KoboCollect as %s: Get Blank Form should now list all '
            'CIPRB forms (including Safe Surgery).' % user))
