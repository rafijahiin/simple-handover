"""
Export the Bandhu client (Mother List / F-1.1) registry as a CSV and upload it
as a form_media attachment to the Bandhu Kobo forms so they can auto-fill
demographics via pulldata() — the digital equivalent of the paper Mother List
lookup. Mirrors export_phd_clients.py.

  - Mother List (F-1.1) uses it to warn on a duplicate ID.
  - Service Log + Activity & Operations use it so that when a worker types a
    client ID, Kobo shows the registered name/TG read-only (confirming the
    right person before filling service fields).

CSV columns (lookup key first, the rest display):
    id_no, name, father_name, birth_year, age, tg, address, spot

Run after Bandhu Client approval (auto-hooked via programs/signals.py) or:
    python manage.py export_bandhu_clients --upload
Without --upload it only writes the CSV locally (dry run).
"""
import csv
import datetime
import io
import logging
import os

import requests
from django.core.management.base import BaseCommand

from programs.models import Client

logger = logging.getLogger(__name__)

CSV_FILENAME = 'bandhu_clients.csv'
KOBO_BASE = 'https://kf.kobotoolbox.org'

# All three Bandhu forms get the CSV.
BANDHU_FORM_UIDS = [
    ('ar4muzSPxzhqd9XxVvWXjx', 'Bandhu 0 — Mother List'),
    ('a7PgkrZcH8gMxqsdgkf6fF', 'Bandhu 1 — Service Log'),
    ('a6nEhvxFfDr2xPpcqnYw4f', 'Bandhu 2 — Activity & Operations'),
]

# Unified TG code → label (matches build_bandhu_forms tg_code list).
TG_LABELS = {
    '01': 'MSM', '02': 'MSW', '03': 'FSW',
    '04': 'EVA', '05': 'TG/Hijra', '06': 'Others',
}


def _norm_id(raw) -> str:
    """Same normalisation the handlers apply on submission (trim + upper)."""
    return (str(raw or '')).strip().upper()


def build_csv():
    """Generate the CSV in memory. Returns (csv_bytes, row_count).

    Excludes stub clients — placeholder rows the service webhooks create when a
    form references an unregistered ID (name 'Unknown' / empty). A real Mother
    List registration always sets a name, so only those are exported (mirrors
    the PHD rule)."""
    qs = (
        Client.objects
        # Bandhu registration is auto-approved, so APPROVED == every real
        # registered client (stubs are excluded by the name filters below).
        .filter(organisation='Bandhu', approval_status=Client.APPROVED)
        .exclude(name='')
        .exclude(name='Unknown')
        .order_by('client_id')
    )
    this_year = datetime.date.today().year

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(['id_no', 'name', 'father_name', 'birth_year', 'age',
                     'tg', 'address', 'spot'])
    count = 0
    for c in qs.iterator():
        age = (this_year - c.birth_year) if c.birth_year else ''
        writer.writerow([
            _norm_id(c.client_id),
            c.name,
            getattr(c, 'father_name', '') or '',
            c.birth_year or '',
            age,
            TG_LABELS.get(getattr(c, 'target_group_code', ''), ''),
            (c.current_address or '').replace('\n', ' ').strip(),
            getattr(c, 'spot_name', '') or '',
        ])
        count += 1
    return buf.getvalue().encode('utf-8'), count


def _kobo_token() -> str:
    from django.conf import settings
    return (getattr(settings, 'KOBO_API_TOKEN', '')
            or os.environ.get('KOBO_TOKEN', '')).strip()


def upload_to_kobo(csv_bytes: bytes, stdout) -> bool:
    """Replace the existing bandhu_clients.csv attachment on every Bandhu form."""
    token = _kobo_token()
    if not token:
        stdout.write('  KOBO_TOKEN not set — skipping upload (dry run).')
        return False
    headers = {'Authorization': f'Token {token}'}
    api = f'{KOBO_BASE}/api/v2'
    all_ok = True
    for uid, label in BANDHU_FORM_UIDS:
        stdout.write(f'  → {label} ({uid})')
        r = requests.get(f'{api}/assets/{uid}/files/', headers=headers, timeout=30)
        if r.status_code == 200:
            for f in r.json().get('results', []):
                meta = f.get('metadata', {}) or {}
                if (f.get('description') == CSV_FILENAME
                        or meta.get('filename') == CSV_FILENAME):
                    requests.delete(f'{api}/assets/{uid}/files/{f["uid"]}/',
                                    headers=headers, timeout=30)
        files = {'content': (CSV_FILENAME, csv_bytes, 'text/csv')}
        data = {'file_type': 'form_media', 'description': CSV_FILENAME,
                'metadata': '{"filename": "bandhu_clients.csv"}'}
        r = requests.post(f'{api}/assets/{uid}/files/', headers=headers,
                          files=files, data=data, timeout=60)
        if r.status_code not in (200, 201):
            stdout.write(f'     FAILED ({r.status_code}): {r.text[:200]}')
            logger.error('Bandhu CSV upload failed for %s: %s %s', uid,
                         r.status_code, r.text[:300])
            all_ok = False
        else:
            stdout.write('     uploaded')
    return all_ok


def redeploy_forms(stdout) -> bool:
    """Redeploy each Bandhu form so Enketo re-transforms with the fresh CSV.
    (Enketo inlines the external CSV at deploy time, keyed on the form version,
    so the media swap alone is invisible until a redeploy bumps the version.)"""
    token = _kobo_token()
    if not token:
        return False
    headers = {'Authorization': f'Token {token}'}
    api = f'{KOBO_BASE}/api/v2'
    all_ok = True
    for uid, label in BANDHU_FORM_UIDS:
        v = requests.get(f'{api}/assets/{uid}/versions/?limit=1',
                         headers=headers, timeout=30)
        try:
            vhash = v.json()['results'][0]['uid']
        except (ValueError, KeyError, IndexError):
            stdout.write(f'  redeploy {label}: no version — skipped')
            all_ok = False
            continue
        r = requests.patch(f'{api}/assets/{uid}/deployment/', headers=headers,
                           json={'version_id': vhash, 'active': True}, timeout=60)
        if r.status_code in (200, 201):
            stdout.write(f'  redeployed {label}')
        else:
            stdout.write(f'  redeploy {label} FAILED ({r.status_code}): {r.text[:160]}')
            all_ok = False
    return all_ok


class Command(BaseCommand):
    help = ('Export approved Bandhu clients as bandhu_clients.csv. With --upload, '
            'attach to the 3 Bandhu Kobo forms as form_media and redeploy.')

    def add_arguments(self, parser):
        parser.add_argument('--upload', action='store_true',
                            help='Attach the CSV to the Bandhu forms and redeploy.')

    def handle(self, *args, **options):
        self.stdout.write('\nExport Bandhu clients (Mother List -> bandhu_clients.csv)\n')
        csv_bytes, n = build_csv()
        self.stdout.write(f'  {n} approved client(s), {len(csv_bytes)} bytes')
        if not options['upload']:
            self.stdout.write('  (dry run — pass --upload to push to Kobo)')
            return
        if upload_to_kobo(csv_bytes, self.stdout):
            redeploy_forms(self.stdout)
        self.stdout.write(self.style.SUCCESS('  done'))
