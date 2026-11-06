# -*- coding: utf-8 -*-
"""
Build (and optionally provision) the shared "No Reporting Today" Kobo form.

This is the field-facing zero-day return: on a day a centre had no activity, the
worker opens this one form, picks their centre + date + reason, and submits. The
webhook (programs.nil_handlers.handle_no_report) records a NilReport at PENDING
so it flows through the normal approval and immediately keeps the centre from
being flagged "silent" on the daily-reporting widget.

One shared form serves every partner — the centre choice carries the org.

Usage:
    python manage.py build_no_report_form                 # just write the .xlsx
    KOBO_TOKEN=... KOBO_WEBHOOK_SECRET=...  \\
        python manage.py build_no_report_form --provision # create + deploy + wire

--provision needs settings.KOBO_API_TOKEN (or env KOBO_TOKEN) and
settings.KOBO_WEBHOOK_SECRET (or env KOBO_WEBHOOK_SECRET).
"""
import os
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from programs.management.commands.build_bandhu_forms import _sr, _ch, _wb, KOBO_BASE, OUTDIR
from programs.models import ServiceCenter

FORM_ID    = 'no_report_v1'
FORM_TITLE = 'No Reporting Today'
FORM_FILE  = 'No_Reporting_Today.xlsx'
APP_BASE   = 'https://web-production-091fa.up.railway.app'

_REASONS = [
    ('centre_closed', 'Centre closed',           'কেন্দ্র বন্ধ'),
    ('holiday',       'Holiday',                  'ছুটির দিন'),
    ('no_clients',    'No clients / no activity', 'কোনো ক্লায়েন্ট/কার্যক্রম নেই'),
    ('staff_absent',  'Staff absent',             'কর্মী অনুপস্থিত'),
    ('other',         'Other',                    'অন্যান্য'),
]


def _survey():
    return [
        _sr('begin_group', 'grp_meta', 'Submission info', 'তথ্য প্রেরণ'),
        _sr('geopoint', 'location',
            'GPS location (step outside if no signal)', 'জিপিএস অবস্থান', required='yes'),
        _sr('text', 'enumerator_name', 'Your name', 'আপনার নাম', required='yes'),
        _sr('end_group', 'grp_meta'),
        _sr('select_one nr_centre', 'center_code',
            'Wellness Centre', 'ওয়েলনেস সেন্টার',
            'Choose your centre', 'yes',
            hint_bn='আপনার কেন্দ্র নির্বাচন করুন'),
        _sr('date', 'report_date',
            'Date with no activity', 'যে তারিখে কার্যক্রম ছিল না',
            '', 'yes', default='today()'),
        _sr('select_one nr_reason', 'nr_reason', 'Reason', 'কারণ', '', 'yes'),
        _sr('text', 'nr_note',
            'Note (optional)', 'মন্তব্য (ঐচ্ছিক)'),
    ]


def _choices():
    rows = []
    # PHD + Bandhu only — CIPRB (monitoring) and UNFPA (oversight) do not do
    # field collection, so they have no zero-day return to file.
    centres = (ServiceCenter.objects
               .filter(is_active=True, organisation__in=['PHD', 'Bandhu'])
               .order_by('organisation', 'name'))
    for c in centres:
        label = f'{c.name} ({c.organisation})'
        rows.append(_ch('nr_centre', c.code, label, label))
    for v, en, bn in _REASONS:
        rows.append(_ch('nr_reason', v, en, bn))
    return rows


# ─── Kobo provisioning (headless, via the API token) ──────────────────────────

def _api():
    return f'{KOBO_BASE}/api/v2'


def _find_by_title(title, H):
    r = requests.get(f'{_api()}/assets/', headers=H, params={'limit': 300}, timeout=30)
    for a in r.json().get('results', []):
        if a.get('name') == title:
            return a['uid']
    return None


def _import_create(path, title, H, out):
    with open(path, 'rb') as fh:
        files = {'file': (os.path.basename(path), fh,
                          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
        r = requests.post(f'{_api()}/imports/', headers=H,
                          files=files, data={'library': 'false', 'name': title}, timeout=120)
    if r.status_code not in (200, 201):
        out.write(f'  import FAILED ({r.status_code}): {r.text[:200]}'); return None
    imp_url = r.json().get('url') or f"{_api()}/imports/{r.json()['uid']}/"
    for _ in range(40):
        time.sleep(1.5)
        s = requests.get(imp_url, headers=H, timeout=30)
        if s.status_code != 200:
            continue
        b = s.json()
        if b.get('status') == 'complete':
            for key in ('created', 'updated'):
                items = b.get('messages', {}).get(key) or []
                if items and items[0].get('uid'):
                    return items[0]['uid']
            return _find_by_title(title, H)
        if b.get('status') in ('error', 'errored'):
            out.write(f'  import error: {b}'); return None
    return None


def _deploy(uid, H, out):
    asset = requests.get(f'{_api()}/assets/{uid}/', headers=H, timeout=30).json()
    vid = asset.get('version_id')
    r = requests.post(f'{_api()}/assets/{uid}/deployment/', headers=H,
                      json={'active': True, 'version_id': vid}, timeout=60)
    if r.status_code in (200, 201):
        return True
    r2 = requests.patch(f'{_api()}/assets/{uid}/deployment/', headers=H,
                        json={'active': True, 'version_id': vid}, timeout=60)
    return r2.status_code in (200, 201)


def _wire_webhook(uid, secret, H, out):
    endpoint = f'{APP_BASE}/webhook/programs/form/{FORM_ID}/'
    ex = requests.get(f'{_api()}/assets/{uid}/hooks/', headers=H, timeout=30).json()
    for h in ex.get('results', []):
        if h.get('endpoint') == endpoint:
            requests.delete(f'{_api()}/assets/{uid}/hooks/{h["uid"]}/', headers=H, timeout=30)
    r = requests.post(f'{_api()}/assets/{uid}/hooks/', headers=H, json={
        'name': 'SIMPLE Railway',
        'endpoint': endpoint,
        'active': True,
        'export_type': 'json',
        'email_notification': False,
        'settings': {'custom_headers': {'Authorization': f'Token {secret}'}},
    }, timeout=60)
    return endpoint if r.status_code in (200, 201) else None


def _allow_anon(uid, H):
    r = requests.post(f'{_api()}/assets/{uid}/permission-assignments/', headers=H, json={
        'user': f'{KOBO_BASE}/api/v2/users/AnonymousUser/',
        'permission': f'{KOBO_BASE}/api/v2/permissions/add_submissions/',
    }, timeout=30)
    return r.status_code in (200, 201, 400)


def _collect_link(uid, H):
    a = requests.get(f'{_api()}/assets/{uid}/', headers=H, timeout=30).json()
    links = a.get('deployment__links') or {}
    return links.get('offline_url') or links.get('url') or f'{KOBO_BASE}/#/forms/{uid}/landing'


class Command(BaseCommand):
    help = 'Build the shared "No Reporting Today" Kobo form (and optionally provision it).'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', default=OUTDIR)
        parser.add_argument('--provision', action='store_true',
            help='Create/import the asset on Kobo, deploy it, wire the webhook, allow anonymous submissions.')

    def handle(self, *args, **options):
        out = options['output_dir']
        os.makedirs(out, exist_ok=True)
        survey, choices = _survey(), _choices()
        path = os.path.join(out, FORM_FILE)
        _wb(FORM_ID, FORM_TITLE, survey, choices).save(path)
        self.stdout.write(self.style.SUCCESS(
            f'  OK  {FORM_FILE}  ({len(survey)} survey rows, {len(choices)} choices)  id: {FORM_ID}'))

        if not options['provision']:
            self.stdout.write(f'\nWritten to {os.path.abspath(path)}\n(run with --provision to push to Kobo)')
            return

        token = (getattr(settings, 'KOBO_API_TOKEN', '') or os.environ.get('KOBO_TOKEN', '')).strip()
        secret = (getattr(settings, 'KOBO_WEBHOOK_SECRET', '') or os.environ.get('KOBO_WEBHOOK_SECRET', '')).strip()
        if not token:
            self.stdout.write(self.style.ERROR('KOBO_API_TOKEN/KOBO_TOKEN not set — cannot --provision.')); return
        if not secret:
            self.stdout.write(self.style.ERROR('KOBO_WEBHOOK_SECRET not set — cannot wire the webhook.')); return
        H = {'Authorization': f'Token {token}'}

        self.stdout.write('  provisioning…')
        # Idempotent: drop any existing asset with this exact title first.
        old = _find_by_title(FORM_TITLE, H)
        if old:
            requests.delete(f'{_api()}/assets/{old}/', headers=H, timeout=30)
            self.stdout.write(f'    removed old copy ({old})')
        uid = _import_create(path, FORM_TITLE, H, self.stdout)
        if not uid:
            self.stdout.write(self.style.ERROR('    import failed')); return
        self.stdout.write(f'    imported  uid={uid}')
        self.stdout.write('    deployed' if _deploy(uid, H, self.stdout) else self.style.ERROR('    deploy FAILED'))
        ep = _wire_webhook(uid, secret, H, self.stdout)
        self.stdout.write(f'    webhook   {ep}' if ep else self.style.ERROR('    webhook FAILED'))
        self.stdout.write('    anon submissions enabled' if _allow_anon(uid, H) else self.style.ERROR('    anon FAILED'))
        self.stdout.write(self.style.SUCCESS(f'\n  COLLECT LINK:  {_collect_link(uid, H)}\n  id_string:     {FORM_ID}'))
