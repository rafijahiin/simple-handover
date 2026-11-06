"""
Backstop re-sync of the per-org client lookup CSVs (phd_clients.csv /
bandhu_clients.csv) attached to the Kobo forms.

The Client post_save signal pushes these best-effort in a background thread; if
that thread is cut short (worker recycled mid-run), a form can be left with a
stale lookup CSV — or a current CSV but a stale Enketo transform (its redeploy
was the part that got dropped). Field workers then see "not in Mother List" for
a client who IS registered.

Run this on a schedule (e.g. every 15 min, Railway cron) to self-heal. It is
idempotent and quiet when everything is in sync:

  - Re-uploads + redeploys a form when its attached CSV has DRIFTED from the
    live data (catches a dropped upload).
  - Also re-uploads + redeploys when a client changed in the last
    RECENT_MINUTES (catches a dropped *redeploy*, where the CSV is current but
    the transform is stale — exactly the failure we saw in the field).
  - Otherwise does nothing — no needless version bumps.

    python manage.py resync_client_csvs
"""
import datetime

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from programs.models import Client
from programs.management.commands import export_phd_clients as phd
from programs.management.commands import export_bandhu_clients as bandhu
from programs.management.commands import export_fistula_clients as fistula
from fistula.ciprb_models import CIPRBFistulaCase

KOBO_API = 'https://kf.kobotoolbox.org/api/v2'
RECENT_MINUTES = 20


def _norm(b) -> str:
    """Compare CSVs by content, ignoring line-ending / trailing-whitespace noise
    so we don't re-sync on cosmetic differences."""
    return (b or b'').decode('utf-8', 'ignore').replace('\r\n', '\n').strip()


def _attached_csv(uid, csv_filename, headers):
    """The bytes of the csv_filename currently attached to the form, or b'' if
    none, or None on a fetch error (treated as 'unknown' → don't force-sync)."""
    r = requests.get(f'{KOBO_API}/assets/{uid}/files/', headers=headers, timeout=30)
    if r.status_code != 200:
        return None
    for f in r.json().get('results', []):
        meta = f.get('metadata', {}) or {}
        if f.get('description') == csv_filename or meta.get('filename') == csv_filename:
            try:
                return requests.get(f['content'], headers=headers, timeout=30).content
            except Exception:
                return None
    return b''


class Command(BaseCommand):
    help = ('Backstop: re-sync phd_clients.csv / bandhu_clients.csv to the Kobo '
            'forms when drifted or after a recent client change. Safe to run on a '
            'schedule; quiet when in sync.')

    def handle(self, *args, **options):
        token = phd._kobo_token()
        if not token:
            self.stdout.write('KOBO_TOKEN not set — nothing to do.')
            return
        headers = {'Authorization': f'Token {token}'}
        cutoff = timezone.now() - datetime.timedelta(minutes=RECENT_MINUTES)

        # `recent` checks whether the org's source data changed in the last
        # RECENT_MINUTES — this catches a dropped *redeploy* (CSV current, but
        # the Enketo transform stale). PHD/Bandhu source from Client; the CIPRB
        # fistula registry sources from CIPRBFistulaCase, so each org carries
        # its own recent-change resolver.
        def _client_recent(o):
            return Client.objects.filter(
                organisation=o, updated_at__gte=cutoff).exists()

        def _fistula_recent(_o):
            return CIPRBFistulaCase.objects.filter(updated_at__gte=cutoff).exists()

        for mod, org, uids, fname, recent_fn in [
            (phd,    'PHD',    phd.PHD_FORM_UIDS,       phd.CSV_FILENAME,    _client_recent),
            (bandhu, 'Bandhu', bandhu.BANDHU_FORM_UIDS, bandhu.CSV_FILENAME, _client_recent),
            (fistula, 'Fistula', fistula.FISTULA_FORM_UIDS, fistula.CSV_FILENAME, _fistula_recent),
        ]:
            try:
                csv_bytes, n = mod.build_csv()
                want = _norm(csv_bytes)
                drift = any(_norm(_attached_csv(uid, fname, headers)) != want
                            for uid, _label in uids)
                recent = recent_fn(org)
                if drift or recent:
                    self.stdout.write(
                        f'{org}: re-syncing ({n} clients; drift={drift}, '
                        f'recent_change={recent})')
                    if mod.upload_to_kobo(csv_bytes, self.stdout):
                        mod.redeploy_forms(self.stdout)
                else:
                    self.stdout.write(f'{org}: in sync ({n} clients) — skipped')
            except Exception as exc:
                # Never let one org's failure stop the other; cron will retry.
                self.stderr.write(f'{org}: resync failed — {exc!r}')
        self.stdout.write(self.style.SUCCESS('resync_client_csvs done'))
