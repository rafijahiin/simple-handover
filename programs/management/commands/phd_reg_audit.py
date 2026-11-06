"""
Audit the PHD FSW Registration (Mother List) form in Kobo, to explain why the
dashboard count differs from the Kobo submission count.

The dashboard shows distinct APPROVED client_id (id_no). Kobo shows raw
submissions. This command reads the live Kobo data and reports:
  - total submissions
  - distinct id_no (normalised trim+upper, as handle_phd_registration does)
  - blank / missing id_no
  - duplicate id_no (same FSW submitted more than once) and how many
    submissions are "extra" because of duplicates

Reads Kobo only (reachable via `railway run`); does not touch the database.

  railway run python manage.py phd_reg_audit
"""
import collections

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

KOBO_BASE = 'https://kf.kobotoolbox.org/api/v2'
REG_ASSET = 'aGWfLrP2yNXqnAiBKuvVgv'   # PHD-1 FSW Registration (Mother List)
ID_FIELD = 'id_no'
PAGE = 500
TIMEOUT = 60


def _token():
    return (getattr(settings, 'KOBO_API_TOKEN', '')
            or __import__('os').environ.get('KOBO_TOKEN', '')).strip()


def _norm(v):
    return str(v or '').strip().upper()


def _extract(row, field):
    """id_no may arrive flat or group-prefixed (grp/id_no). Suffix-match."""
    if field in row:
        return row[field]
    for k, v in row.items():
        if k.rsplit('/', 1)[-1] == field:
            return v
    return ''


class Command(BaseCommand):
    help = 'Audit the PHD registration (Mother List) form submissions in Kobo.'

    def add_arguments(self, parser):
        parser.add_argument('--uid', default=REG_ASSET)
        parser.add_argument('--field', default=ID_FIELD)

    def handle(self, *args, **opts):
        token = _token()
        if not token:
            self.stderr.write('KOBO_TOKEN not set; run under `railway run`.')
            return

        uid, field = opts['uid'], opts['field']
        headers = {'Authorization': 'Token ' + token}
        url = ('%s/assets/%s/data/?sort={"_id":1}&limit=%d'
               % (KOBO_BASE, uid, PAGE))

        total = 0
        blank = 0
        counts = collections.Counter()
        while url:
            r = requests.get(url, headers=headers, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
            for row in data.get('results', []):
                total += 1
                raw = _norm(_extract(row, field))
                if not raw:
                    blank += 1
                else:
                    counts[raw] += 1
            url = data.get('next')
            self.stdout.write('  ...read %d' % total, ending='\r')

        distinct = len(counts)
        dup_ids = {k: v for k, v in counts.items() if v > 1}
        extra = sum(v - 1 for v in dup_ids.values())

        self.stdout.write('\n')
        self.stdout.write(self.style.MIGRATE_HEADING(
            'PHD Registration (Mother List) — Kobo audit'))
        self.stdout.write('  asset                : %s' % uid)
        self.stdout.write('  total submissions    : %d' % total)
        self.stdout.write('  blank/missing %-7s: %d' % (field, blank))
        self.stdout.write('  distinct %-12s: %d' % (field, distinct))
        self.stdout.write('  duplicate %-11s: %d ids repeated' % (field, len(dup_ids)))
        self.stdout.write('  extra dup submissions: %d' % extra)
        self.stdout.write('  (total = distinct + extra + blank: %d = %d + %d + %d)'
                          % (total, distinct, extra, blank))
        if dup_ids:
            top = sorted(dup_ids.items(), key=lambda kv: -kv[1])[:10]
            self.stdout.write('  top repeated ids     : '
                              + ', '.join('%s x%d' % (k, v) for k, v in top))
        self.stdout.write(self.style.WARNING(
            '\nDashboard shows distinct APPROVED id_no. If distinct above is '
            'close to the dashboard number, the gap is re-submissions + pending '
            'approval, not lost data. If distinct is far above the dashboard '
            'number, registrations are stuck PENDING or never ingested.'))
