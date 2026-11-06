"""
Export the PHD client (Master List / Mother List) registry as a CSV and
upload it as a form_media attachment to the PHD Kobo forms so they can
auto-fill demographics via pulldata().

This is the digital equivalent of the paper "Master List" lookup — when
an enumerator types 1-0001 in Form 2 (Service Log), Kobo reads this CSV
and displays her name / age / address / status read-only, confirming they
have the right woman before she fills any clinical fields.

CSV columns (kept in sync with the Master List headers):
    id_no          — the lookup key. Normalised (trim + upper).
    name           — display.
    mother_name    — display.
    birth_year     — display.
    age            — computed (current year - birth_year).
    address        — Permanent address.
    marital_status — Label (Married / Single / Widowed / ...).
    education      — Label (Illiterate / Primary / ... / Graduate-Masters).
    has_nid        — Yes / No.
    uses_fp        — Yes / No.
    status         — Active / Jailed / Relocated / ...

Run on Railway after Client approval (auto-hooked in step 3) or manually:

    python manage.py export_phd_clients --upload

Without --upload the command just writes /tmp/phd_clients.csv and prints
a summary (useful for dry-runs / debugging without touching Kobo).
"""
import csv
import datetime
import io
import logging
import os
import sys

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from programs.models import Client

logger = logging.getLogger(__name__)

# Both PHD forms get the CSV — Form 1 uses it to warn on duplicate IDs,
# Form 2 uses it to auto-fill demographics via pulldata().
PHD_FORM_UIDS = [
    ('aGWfLrP2yNXqnAiBKuvVgv', 'PHD 1 — FSW Registration'),
    ('aDv2CZapM2eSqijKr2WZKc', 'PHD 2 — Service Log'),
]

CSV_FILENAME = 'phd_clients.csv'
KOBO_BASE = 'https://kf.kobotoolbox.org'

MARITAL_LABELS = {
    '1': 'Single', '2': 'Married', '3': 'Widowed',
    '4': 'Separated', '5': 'Divorced', '6': 'Other',
}
EDUCATION_LABELS = {
    '1': 'Illiterate', '2': 'Primary', '3': 'Secondary',
    '4': 'Higher Secondary', '5': 'Graduate / Masters', '6': 'Other',
}
STATUS_LABELS = dict(Client.STATUS_CHOICES)


def _yes_no(v) -> str:
    if v is None:
        return ''
    return 'Yes' if v else 'No'


def _norm_id(raw: str) -> str:
    """Same normalisation rule the backend handlers will apply on submission:
    strip whitespace, uppercase. Lets enumerators type ' 1-0001 '
    and still match the canonical '1-0001'."""
    return (raw or '').strip().upper()


def build_csv() -> tuple[bytes, int]:
    """Generate the CSV in memory. Returns (csv_bytes, row_count).

    Excludes 'stub' clients — placeholder Client rows that the webhook
    auto-creates when a service form references an unregistered ID.
    Stubs have no name (and usually no birth_year / address). If they
    were exported the Service Log's pulldata() would find the row, see
    an empty name field, and fire the 'not registered' warning anyway
    — confusing the enumerator. A real registration must come from
    Form 1 (FSW Registration), and that always sets at least name."""
    qs = (
        Client.objects
        # Include PENDING as well as APPROVED. A freshly-registered FSW must be
        # loggable immediately — field workers cannot wait for the PHD manager's
        # approval to record her services — so her PENDING registration still
        # flows into the Service Log's pulldata(). REJECTED registrations are
        # excluded: a rejected FSW correctly drops back out of the lookup.
        .filter(organisation='PHD',
                approval_status__in=[Client.APPROVED, Client.PENDING])
        .exclude(name='')         # drop stubs
        .order_by('client_id')
    )
    this_year = datetime.date.today().year

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        'id_no', 'name', 'mother_name', 'birth_year', 'age',
        'address', 'marital_status', 'education',
        'has_nid', 'uses_fp', 'status',
    ])

    count = 0
    for c in qs.iterator():
        age = (this_year - c.birth_year) if c.birth_year else ''
        writer.writerow([
            _norm_id(c.client_id),
            c.name,
            c.mother_name,
            c.birth_year or '',
            age,
            (c.current_address or '').replace('\n', ' ').strip(),
            MARITAL_LABELS.get(c.marital_status, ''),
            EDUCATION_LABELS.get(c.education_level, ''),
            _yes_no(c.has_nid),
            _yes_no(c.uses_fp_method),
            STATUS_LABELS.get(c.current_status, ''),
        ])
        count += 1

    return buf.getvalue().encode('utf-8'), count


def _kobo_token() -> str:
    return (
        getattr(settings, 'KOBO_API_TOKEN', '') or
        os.environ.get('KOBO_TOKEN', '')
    ).strip()


def upload_to_kobo(csv_bytes: bytes, stdout) -> bool:
    """Replace the existing phd_clients.csv attachment on every PHD form."""
    token = _kobo_token()
    if not token:
        stdout.write('  KOBO_API_TOKEN not set — skipping upload (dry run).')
        return False

    headers = {'Authorization': f'Token {token}'}
    api = f'{KOBO_BASE}/api/v2'
    all_ok = True

    for uid, label in PHD_FORM_UIDS:
        stdout.write(f'  → {label} ({uid})')

        # 1. Delete any previous phd_clients.csv attached to this form.
        r = requests.get(f'{api}/assets/{uid}/files/', headers=headers, timeout=30)
        if r.status_code == 200:
            for f in r.json().get('results', []):
                desc = f.get('description', '') or ''
                meta = f.get('metadata', {}) or {}
                if desc == CSV_FILENAME or meta.get('filename') == CSV_FILENAME:
                    requests.delete(
                        f'{api}/assets/{uid}/files/{f["uid"]}/',
                        headers=headers, timeout=30,
                    )

        # 2. Upload the fresh CSV.
        files = {
            'content': (CSV_FILENAME, csv_bytes, 'text/csv'),
        }
        data = {
            'file_type': 'form_media',
            'description': CSV_FILENAME,
            'metadata': '{"filename": "phd_clients.csv"}',
        }
        r = requests.post(
            f'{api}/assets/{uid}/files/',
            headers=headers, files=files, data=data, timeout=60,
        )
        if r.status_code not in (200, 201):
            stdout.write(f'     FAILED ({r.status_code}): {r.text[:200]}')
            logger.error('Kobo CSV upload failed for %s: %s %s',
                         uid, r.status_code, r.text[:300])
            all_ok = False
        else:
            stdout.write('     uploaded')

    return all_ok


def redeploy_forms(stdout) -> bool:
    """Redeploy both PHD forms so Enketo re-transforms with the fresh CSV.

    CRITICAL: replacing the form_media CSV via the API is NOT enough.
    Enketo inlines the external CSV into its cached form transform at
    DEPLOY time, keyed on the form version. Until the form is redeployed,
    Enketo keeps serving the transform it built at the last deploy — with
    the OLD CSV — so a newly-registered FSW shows 'not in Master List'
    even though the attached CSV already contains her.

    The redeploy (PATCH /deployment/ with the latest version hash) bumps
    the Enketo form hash (which includes the media hash) and forces a
    fresh transform that picks up the new CSV.
    """
    token = _kobo_token()
    if not token:
        return False
    headers = {'Authorization': f'Token {token}'}
    api = f'{KOBO_BASE}/api/v2'
    all_ok = True

    for uid, label in PHD_FORM_UIDS:
        # Latest version hash from /versions/ — the only reliable source
        # (asset.version_id can lag behind the newest content version).
        v = requests.get(f'{api}/assets/{uid}/versions/?limit=1',
                         headers=headers, timeout=30)
        try:
            vhash = v.json()['results'][0]['uid']
        except (ValueError, KeyError, IndexError):
            stdout.write(f'  redeploy {label}: no version found — skipped')
            all_ok = False
            continue

        r = requests.patch(
            f'{api}/assets/{uid}/deployment/',
            headers=headers,
            json={'version_id': vhash, 'active': True},
            timeout=60,
        )
        if r.status_code in (200, 201):
            stdout.write(f'  redeployed {label}')
        else:
            stdout.write(f'  redeploy {label} FAILED ({r.status_code}): {r.text[:160]}')
            logger.error('Kobo redeploy failed for %s: %s %s',
                         uid, r.status_code, r.text[:300])
            all_ok = False

    return all_ok


class Command(BaseCommand):
    help = (
        'Export the PHD Master List (approved Client rows) as phd_clients.csv. '
        'With --upload, also attaches it to both PHD Kobo forms as form_media '
        'so the forms can auto-fill demographics via pulldata().'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--upload', action='store_true',
            help='Upload the CSV to both PHD forms in Kobo. Without this '
                 'flag only writes /tmp/phd_clients.csv (dry run).',
        )

    def handle(self, *args, **options):
        upload = options['upload']
        self.stdout.write('\nExport PHD clients (Master List → phd_clients.csv)\n')

        csv_bytes, n = build_csv()
        if n == 0:
            self.stdout.write(self.style.WARNING(
                '  Zero approved PHD Client rows — nothing to export.\n'
                '  (Register some FSWs via Form 1 first, then approve them.)'
            ))
            return

        # Always write a local copy for debugging / verification.
        out_path = os.path.join('/tmp' if os.name != 'nt' else os.environ.get('TEMP', '.'),
                                CSV_FILENAME)
        try:
            with open(out_path, 'wb') as fh:
                fh.write(csv_bytes)
            self.stdout.write(f'  wrote {n} rows → {out_path}')
        except OSError as exc:
            self.stdout.write(self.style.WARNING(f'  could not write {out_path}: {exc}'))

        if not upload:
            self.stdout.write(self.style.NOTICE(
                '\n  Dry run — pass --upload to push to Kobo.\n'
            ))
            return

        ok = upload_to_kobo(csv_bytes, self.stdout)
        if ok:
            # The redeploy is what actually makes Enketo pick up the new
            # CSV — see redeploy_forms() docstring. Without it, the upload
            # is invisible to the field forms.
            self.stdout.write('\n  Redeploying so Enketo re-transforms with the new CSV…')
            redeploy_forms(self.stdout)
            self.stdout.write(self.style.SUCCESS(
                '\n  Done — CSV live + forms redeployed.\n'
            ))
        else:
            self.stdout.write(self.style.ERROR(
                '\n  Upload failed (see errors above). Retry on the next sync.\n'
            ))
            sys.exit(1)
