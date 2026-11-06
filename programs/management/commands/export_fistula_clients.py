"""
Export the registered CIPRB fistula patients (Suspected-stage rows of
CIPRBFistulaCase) as a CSV and upload it as a form_media attachment to the
CIPRB Fistula Question Bank form, so the later-stage workflow can:

  * populate the `select_one_from_file fistula_clients.csv` dropdown the
    field worker picks from at Diagnosed / Referred / Repaired / Rehabilitated,
  * auto-fill her name / age / husband / village via pulldata() (read-only
    confirmation that the worker has the right woman),
  * block re-registration of an existing ID at the Suspected stage (the
    registration form's pulldata duplicate check reads the same CSV).

This is the fistula equivalent of the PHD Master List lookup. The CSV is the
digital registry: one row per registered patient, keyed on her patient_code.

CSV columns:
    name           — the select_one_from_file STORED VALUE. Set to the id_no
                     so the dropdown stores the patient's ID (Kobo uses the
                     CSV `name` column as the saved value by default).
    label          — the select_one_from_file DISPLAY label,
                     "1-0001 — Rahima (Sunamganj)".
    id_no          — the pulldata() lookup key (= the same id). Normalised
                     (trim + upper) so ' 1-0001 ' matches the canonical '1-0001'.
    patient_name   — the woman's name, for pulldata() read-only confirmation.
    district       — for reference / optional cascade later.
    age            — display.
    husband        — display.
    village        — display.
    suspected_date — display (when she was first registered).

Run on Railway after a Suspected-stage submission (auto-hooked via
programs.signals) or manually:

    python manage.py export_fistula_clients --upload

Without --upload the command just writes the CSV locally and prints a summary
(useful for dry-runs / debugging without touching Kobo).
"""
import csv
import io
import logging
import os
import sys

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from fistula.ciprb_models import CIPRBFistulaCase

logger = logging.getLogger(__name__)

# The single CIPRB Fistula Question Bank form gets the CSV — its later-stage
# dropdown + pulldata read it, and its Suspected-stage duplicate check too.
FISTULA_FORM_UIDS = [
    ('aH86Euq2AeJ8S9VYdry4PC', 'CIPRB 1 — Fistula Question Bank'),
    ('aso6xsUo8PMYRCzGQBc8Cm', 'CIPRB — Fistula Campaign (Identification)'),
]

CSV_FILENAME = 'fistula_clients.csv'
KOBO_BASE = 'https://kf.kobotoolbox.org'


def _norm_id(raw: str) -> str:
    """Same normalisation the form (translate(normalize-space())) and the
    webhook handler apply: strip whitespace, upper-case. Keeps the CSV key,
    the dropdown value, and the stored patient_code all in sync."""
    return (raw or '').strip().upper()


def build_csv() -> tuple[bytes, int]:
    """Generate the registry CSV in memory. Returns (csv_bytes, row_count).

    Only patients who have a patient_code AND a name are exported — a row
    without a code can't be looked up, and a nameless row would show a blank
    in the dropdown. Both are skipped."""
    qs = (
        CIPRBFistulaCase.objects
        .exclude(patient_code__isnull=True)
        .exclude(patient_code='')
        .exclude(name='')
        .order_by('patient_code')
    )

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    # `name` (= id) is the select_one_from_file stored value, `label` the
    # display. `id_no` (= same id) is the pulldata key; `patient_name` is the
    # woman's name (pulldata can't reuse `name` — that column now holds the id).
    writer.writerow([
        'name', 'label', 'id_no', 'patient_name', 'district',
        'district_slug', 'age', 'husband', 'village', 'suspected_date',
    ])

    count = 0
    for c in qs.iterator():
        idn = _norm_id(c.patient_code)
        # Paper serial leads the label: with server-issued IDs the worker's own
        # register serial is the number she actually knows, so she searches by
        # it ("54 | Shahida ...") and the ID rides along as the stored value.
        serial = (c.case_serial or '').strip()
        parts = [p for p in (serial, c.name, c.village, idn) if p]
        label = ' | '.join(parts)
        writer.writerow([
            idn,
            label,
            idn,
            c.name,
            c.district,
            # Matches the form's `district` choice value so the dropdown's
            # choice_filter shows only the worker's own district's patients.
            (c.district or '').strip().lower().replace(' ', '_'),
            c.age or '',
            c.husband,
            c.village,
            c.suspected_date.isoformat() if c.suspected_date else '',
        ])
        count += 1

    return buf.getvalue().encode('utf-8'), count


def _kobo_token() -> str:
    return (
        getattr(settings, 'KOBO_API_TOKEN', '') or
        os.environ.get('KOBO_TOKEN', '')
    ).strip()


def upload_to_kobo(csv_bytes: bytes, stdout) -> bool:
    """Replace the existing fistula_clients.csv attachment on the CIPRB form."""
    token = _kobo_token()
    if not token:
        stdout.write('  KOBO_API_TOKEN not set — skipping upload (dry run).')
        return False

    headers = {'Authorization': f'Token {token}'}
    api = f'{KOBO_BASE}/api/v2'
    all_ok = True

    for uid, label in FISTULA_FORM_UIDS:
        stdout.write(f'  → {label} ({uid})')

        # 1. Delete any previous fistula_clients.csv attached to this form.
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
            'metadata': '{"filename": "fistula_clients.csv"}',
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
    """Redeploy the CIPRB fistula form so Enketo re-transforms with the fresh CSV.

    CRITICAL: replacing the form_media CSV via the API is NOT enough.
    Enketo inlines the external CSV into its cached form transform at
    DEPLOY time, keyed on the form version. Until the form is redeployed,
    Enketo keeps serving the transform it built at the last deploy — with
    the OLD CSV — so a newly-registered patient is missing from the dropdown
    / pulldata even though the attached CSV already contains her.

    The redeploy (PATCH /deployment/ with the latest version hash) bumps the
    Enketo form hash (which includes the media hash) and forces a fresh
    transform that picks up the new CSV.
    """
    token = _kobo_token()
    if not token:
        return False
    headers = {'Authorization': f'Token {token}'}
    api = f'{KOBO_BASE}/api/v2'
    all_ok = True

    for uid, label in FISTULA_FORM_UIDS:
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
        'Export the registered CIPRB fistula patients (Suspected-stage '
        'CIPRBFistulaCase rows) as fistula_clients.csv. With --upload, also '
        'attaches it to the CIPRB Fistula Question Bank form as form_media so '
        'the later-stage dropdown + pulldata can find them.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--upload', action='store_true',
            help='Upload the CSV to the CIPRB fistula form in Kobo. Without '
                 'this flag only writes the CSV locally (dry run).',
        )

    def handle(self, *args, **options):
        upload = options['upload']
        self.stdout.write('\nExport CIPRB fistula patients (registry → fistula_clients.csv)\n')

        csv_bytes, n = build_csv()
        if n == 0:
            self.stdout.write(self.style.WARNING(
                '  Zero registered fistula patients — nothing to export.\n'
                '  (Register some at the Suspected stage first.)'
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
            # The redeploy is what actually makes Enketo pick up the new CSV —
            # see redeploy_forms() docstring. Without it, the upload is
            # invisible to the field form.
            self.stdout.write('\n  Redeploying so Enketo re-transforms with the new CSV…')
            redeploy_forms(self.stdout)
            self.stdout.write(self.style.SUCCESS(
                '\n  Done — CSV live + form redeployed.\n'
            ))
        else:
            self.stdout.write(self.style.ERROR(
                '\n  Upload failed (see errors above). Retry on the next sync.\n'
            ))
            sys.exit(1)
