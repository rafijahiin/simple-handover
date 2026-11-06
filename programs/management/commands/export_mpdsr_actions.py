"""
Export the open MPDSR actions (MPDSRAction rows) as a CSV and attach it as
form_media to the CIPRB 10 — MPDSR Action Plan form, so the 'update an action'
mode can:

  * populate the `select_one_from_file mpdsr_actions.csv` dropdown the committee
    picks the action from (by its D-NN id),
  * auto-fill the action's activity / responsible / timeline / district / status
    via pulldata() (read-only confirmation they picked the right one).

This is the Action-Plan equivalent of the fistula registry CSV. The CSV is the
live list of actions, one row per action, keyed on action_id.

CSV columns:
    name        — select_one_from_file STORED VALUE (= action_id, so the
                  dropdown stores 'D-01').
    label       — dropdown DISPLAY, 'D-01 — Train CHCPs… (Dhaka)'.
    action_id   — the pulldata() lookup key (= the same id, normalised).
    activity    — the action text (pulldata confirmation).
    responsible — pulldata confirmation.
    timeline    — target date (pulldata confirmation).
    district    — pulldata confirmation.
    status      — current status label (pulldata confirmation).

Run on Railway after a plan/update submission (auto-hooked via programs.signals)
or manually:

    python manage.py export_mpdsr_actions --upload

Without --upload it just writes the CSV locally + prints a summary (dry run).
"""
import csv
import io
import logging
import os
import sys

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from mpdsr.models import MPDSRAction, ActionStatus, STUB_ACTIVITY_SENTINEL

logger = logging.getLogger(__name__)

# CIPRB 10 — MPDSR Action Plan. Its 'update an action' dropdown + pulldata read
# this CSV.
ACTION_FORM_UIDS = [
    ('auFCf7bfBDtrP6xeW5F2KJ', 'CIPRB 10 — MPDSR Action Plan'),
]

CSV_FILENAME = 'mpdsr_actions.csv'
KOBO_BASE = 'https://kf.kobotoolbox.org'


def _norm_id(raw: str) -> str:
    """Same normalisation the form (translate(normalize-space())) and the
    handler apply: strip + upper-case. Keeps the CSV key, the dropdown value and
    the stored action_id in sync."""
    return (raw or '').strip().upper()


def build_csv() -> tuple[bytes, int]:
    """Generate the open-actions CSV in memory. Returns (csv_bytes, row_count).

    Lists every PENDING or APPROVED action with a real id so the Kobo form can
    (a) offer it in the 'update an action' dropdown and (b) block re-using its id
    in 'new plan'. Including PENDING is deliberate (audit FIX 2026-06): the CSV
    is the form's *working set*, decoupled from the dashboard/reporting gate which
    filters APPROVED separately. Without it a freshly-registered action could not
    be updated until approved, and an approved action vanished from the dropdown
    the moment it was edited (every edit re-enters PENDING) — and two enumerators
    could silently reuse the same id while both were pending. Excluded:
      • REJECTED  — a rejected id stays re-registerable via 'new plan' (recovery);
      • DROPPED   — a cancelled action is done;
      • stub rows — '[awaiting plan record]' placeholders are not real actions."""
    qs = (
        MPDSRAction.objects
        .filter(approval_status__in=('PENDING', 'APPROVED'))
        .exclude(action_id='')
        .exclude(status=ActionStatus.DROPPED)
        .exclude(activity=STUB_ACTIVITY_SENTINEL)
        .order_by('district', 'action_id')
    )

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        'name', 'label', 'action_id', 'activity', 'responsible',
        'timeline', 'district', 'district_slug', 'status',
    ])

    count = 0
    for a in qs.iterator():
        idn = _norm_id(a.action_id)
        short = (a.activity or '').strip().replace('\n', ' ')
        if len(short) > 45:
            short = short[:44] + '…'
        writer.writerow([
            idn,
            f'{idn} — {short} ({a.district})',
            idn,
            (a.activity or '').strip().replace('\n', ' '),
            a.responsible or '',
            a.timeline.isoformat() if a.timeline else '',
            a.district or '',
            (a.district or '').lower().replace(' ', '_'),
            a.get_status_display(),
        ])
        count += 1

    return buf.getvalue().encode('utf-8'), count


def _kobo_token() -> str:
    return (
        getattr(settings, 'KOBO_API_TOKEN', '') or
        os.environ.get('KOBO_TOKEN', '')
    ).strip()


def upload_to_kobo(csv_bytes: bytes, stdout) -> bool:
    """Replace the existing mpdsr_actions.csv attachment on the Action Plan form."""
    token = _kobo_token()
    if not token:
        stdout.write('  KOBO_API_TOKEN not set — skipping upload (dry run).')
        return False

    headers = {'Authorization': f'Token {token}'}
    api = f'{KOBO_BASE}/api/v2'
    all_ok = True

    for uid, label in ACTION_FORM_UIDS:
        stdout.write(f'  → {label} ({uid})')

        # 1. Delete any previous mpdsr_actions.csv attached to this form.
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
        files = {'content': (CSV_FILENAME, csv_bytes, 'text/csv')}
        data = {
            'file_type': 'form_media',
            'description': CSV_FILENAME,
            'metadata': '{"filename": "mpdsr_actions.csv"}',
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
    """Redeploy so Enketo re-transforms with the fresh CSV.

    CRITICAL: replacing the form_media CSV is NOT enough — Enketo inlines the
    external CSV into its cached transform at DEPLOY time. Until the form is
    redeployed, the dropdown / pulldata keep serving the OLD list."""
    token = _kobo_token()
    if not token:
        return False
    headers = {'Authorization': f'Token {token}'}
    api = f'{KOBO_BASE}/api/v2'
    all_ok = True

    for uid, label in ACTION_FORM_UIDS:
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
        'Export the open MPDSR actions as mpdsr_actions.csv. With --upload, also '
        'attaches it to the CIPRB 10 Action Plan form as form_media so the '
        "'update an action' dropdown + pulldata can find them."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--upload', action='store_true',
            help='Upload + redeploy to Kobo. Without it, only writes locally.',
        )

    def handle(self, *args, **options):
        upload = options['upload']
        self.stdout.write('\nExport MPDSR actions (→ mpdsr_actions.csv)\n')

        csv_bytes, n = build_csv()

        out_path = os.path.join('/tmp' if os.name != 'nt' else os.environ.get('TEMP', '.'),
                                CSV_FILENAME)
        try:
            with open(out_path, 'wb') as fh:
                fh.write(csv_bytes)
            self.stdout.write(f'  wrote {n} rows → {out_path}')
        except OSError as exc:
            self.stdout.write(self.style.WARNING(f'  could not write {out_path}: {exc}'))

        if not upload:
            self.stdout.write(self.style.NOTICE('\n  Dry run — pass --upload to push to Kobo.\n'))
            return

        # Always upload — even an empty list keeps the dropdown attached so the
        # select_one_from_file doesn't error; it just shows no rows yet.
        ok = upload_to_kobo(csv_bytes, self.stdout)
        if ok:
            self.stdout.write('\n  Redeploying so Enketo re-transforms with the new CSV…')
            redeploy_forms(self.stdout)
            self.stdout.write(self.style.SUCCESS('\n  Done — CSV live + form redeployed.\n'))
        else:
            self.stdout.write(self.style.ERROR('\n  Upload failed (see above). Retry next sync.\n'))
            sys.exit(1)
