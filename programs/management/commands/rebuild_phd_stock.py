"""Rebuild PHD StockEntry rows from Kobo by SUMMING quantity across every
submission for the same (centre, month, item), instead of the old last-wins
collapse.

Field staff log stock per-issue, so one item/centre/month is submitted many
times. The webhook now accumulates going forward (see
programs.webhook._accumulate_stock); this one-off command corrects the rows that
were written under the old update_or_create behaviour.

Idempotent: replays each Kobo submission through the real _phd_stock handler,
which dedupes on submission _id. Safe to re-run. Read-only against Kobo.

    railway ssh "python manage.py rebuild_phd_stock"
    railway ssh "python manage.py rebuild_phd_stock --dry-run"
"""
import json
import os
import urllib.request
import urllib.parse

from django.core.management.base import BaseCommand
from django.db.models import Sum

from programs.models import StockEntry
from programs.webhook import _flatten_group_keys, _geolocation
from programs import phd_handlers

KOBO_API = 'https://kf.kobotoolbox.org/api/v2'


def _get(url, token):
    req = urllib.request.Request(url, headers={'Authorization': f'Token {token}'})
    return json.load(urllib.request.urlopen(req, timeout=120))


def _phd_service_log_uid(token):
    data = _get(f'{KOBO_API}/assets/?limit=200', token)
    for a in data.get('results', []):
        nm = (a.get('name') or '').lower()
        if 'phd' in nm and 'service' in nm:
            return a['uid']
    return None


def _sl5(label):
    from indicators import phd as P
    from datetime import date
    ps, pe = date(2000, 1, 1), date(2100, 1, 1)
    org = 'PHD'
    print(f'  {label:8}  SL5a condom={P.compute_SL5a(org, ps, pe)}  '
          f'SL5b syph={P.compute_SL5b(org, ps, pe)}  '
          f'SL5c hepB={P.compute_SL5c(org, ps, pe)}  '
          f'SL5d hepC={P.compute_SL5d(org, ps, pe)}  '
          f'SL5e hiv={P.compute_SL5e(org, ps, pe)}')


class Command(BaseCommand):
    help = 'Rebuild PHD StockEntry rows by summing quantity across Kobo submissions.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Fetch and report counts without changing the DB.')

    def handle(self, *args, **opts):
        token = os.environ.get('KOBO_TOKEN', '')
        if not token:
            self.stderr.write('KOBO_TOKEN not set'); return
        uid = _phd_service_log_uid(token)
        if not uid:
            self.stderr.write('PHD Service Log asset not found'); return
        self.stdout.write(f'PHD Service Log asset: {uid}')

        # Pull all submissions, keep the stock ones.
        rows, start = [], 0
        while True:
            q = urllib.parse.urlencode({'start': start, 'limit': 1000})
            d = _get(f'{KOBO_API}/assets/{uid}/data/?{q}', token)
            batch = d.get('results', [])
            if not batch:
                break
            rows += batch
            start += len(batch)
            if len(batch) < 1000:
                break

        def leaf(r, name):
            for k, v in r.items():
                if k.rsplit('/', 1)[-1] == name:
                    return v
            return None

        stock = [r for r in rows if leaf(r, 'record_type') == 'stock']
        self.stdout.write(f'Kobo stock submissions: {len(stock)}')

        before_rows = StockEntry.objects.filter(organisation='PHD').count()
        before_sum = StockEntry.objects.filter(organisation='PHD').aggregate(
            t=Sum('quantity_issued'))['t'] or 0
        self.stdout.write(f'DB PHD StockEntry before: rows={before_rows} '
                          f'quantity_issued_sum={before_sum}')
        print('SL5 before:'); _sl5('before')

        if opts['dry_run']:
            self.stdout.write('--dry-run: no changes made.')
            return

        # Rebuild: clear PHD rows, replay every submission through the real
        # handler (which now accumulates), then restore APPROVED (the historical
        # PHD set was all manager-approved; new live submissions still land
        # PENDING for review).
        StockEntry.objects.filter(organisation='PHD').delete()
        ok = err = 0
        for r in stock:
            payload = _flatten_group_keys(dict(r))
            lat, lng = _geolocation(payload)
            try:
                resp = phd_handlers._phd_stock(payload, lat, lng)
                if resp.status_code in (200, 201):
                    ok += 1
                else:
                    err += 1
            except Exception as exc:  # pragma: no cover
                err += 1
                self.stderr.write(f'  replay error ({leaf(r, "_id")}): {exc}')

        restored = StockEntry.objects.filter(organisation='PHD').update(
            approval_status=StockEntry.APPROVED)

        after_rows = StockEntry.objects.filter(organisation='PHD').count()
        after_sum = StockEntry.objects.filter(organisation='PHD').aggregate(
            t=Sum('quantity_issued'))['t'] or 0
        self.stdout.write(f'Replayed ok={ok} err={err}; rows marked APPROVED={restored}')
        self.stdout.write(f'DB PHD StockEntry after:  rows={after_rows} '
                          f'quantity_issued_sum={after_sum}')
        print('SL5 after:'); _sl5('after')
        self.stdout.write(self.style.SUCCESS('rebuild_phd_stock complete.'))
